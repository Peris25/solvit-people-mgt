from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, get_current_user
)
import jwt
import os

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "employee"


@router.post("/login")
async def login(req: LoginRequest, response: Response):
    db = get_db()
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email, user["role"])
    refresh_token = create_refresh_token(user_id)

    response.set_cookie("access_token", access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")

    return {
        "id": user_id,
        "email": email,
        "full_name": user.get("full_name", ""),
        "role": user["role"],
        "department": user.get("department", ""),
        "employee_id": user.get("employee_id", "")
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}


@router.get("/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return user


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        db = get_db()
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(str(user["_id"]), user["email"], user["role"])
        response.set_cookie("access_token", access_token, httponly=True, secure=False, samesite="lax", max_age=86400, path="/")
        return {"message": "Token refreshed"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
