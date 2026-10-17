"""Bounded employee-document validation and fail-closed ClamAV INSTREAM scanning."""
import asyncio
from io import BytesIO
import os
from pathlib import PurePosixPath
import struct
import warnings
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 20 * 1024 * 1024
MIME = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}


def filename(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(c in value for c in '/\\:') or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise HTTPException(400, 'Use a plain document filename without paths or control characters')
    value = value.strip()
    ext = PurePosixPath(value).suffix.lower()
    if ext not in MIME:
        raise HTTPException(400, 'Allowed files: PDF, JPG, PNG, DOCX and XLSX')
    return value, ext


async def read_bounded(file):
    chunks, size = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk: break
        size += len(chunk)
        if size > MAX_BYTES: raise HTTPException(413, 'File exceeds the 20 MB limit')
        chunks.append(chunk)
    if not size: raise HTTPException(400, 'The document is empty')
    return b''.join(chunks)


def validate_content(content, ext, supplied_mime):
    if supplied_mime and supplied_mime.split(';')[0].strip().lower() not in {MIME[ext], 'application/octet-stream'}:
        raise HTTPException(400, 'File content type does not match its extension')
    try:
        if ext == '.pdf':
            if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-2048:]: raise ValueError()
        elif ext in {'.jpg', '.jpeg', '.png'}:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    if image.format != ('PNG' if ext == '.png' else 'JPEG') or image.width * image.height > 40_000_000: raise ValueError()
                    image.verify()
        else:
            validate_office(content, ext)
    except HTTPException:
        raise
    except (ValueError, OSError, BadZipFile, KeyError, ElementTree.ParseError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, RuntimeError, NotImplementedError, EOFError, SyntaxError):
        raise HTTPException(400, 'The document content is invalid or unsafe for this file type')


def validate_office(content, ext):
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > 2000 or len(set(names)) != len(names) or sum(item.file_size for item in entries) > 100 * 1024 * 1024:
            raise ValueError()
        required = {'[Content_Types].xml', '_rels/.rels', 'word/document.xml' if ext == '.docx' else 'xl/workbook.xml'}
        if not required.issubset(names): raise ValueError()
        for item in entries:
            path = PurePosixPath(item.filename)
            lower = item.filename.lower()
            if path.is_absolute() or '..' in path.parts or '\\' in lower or ':' in lower or item.flag_bits & 1 or any(term in lower for term in ('vbaproject', 'activex/', 'embeddings/')):
                raise ValueError()
            if item.file_size > 20 * 1024 * 1024 or item.file_size > max(1, item.compress_size) * 200:
                raise ValueError()
            # Reading validates ZIP CRCs without ever extracting files to disk.
            data = archive.read(item)
            if lower.endswith(('.xml', '.rels')):
                if len(data) > 4 * 1024 * 1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError()
                root = ElementTree.fromstring(data)
                if lower.endswith('.rels') and any(str(node.attrib.get('TargetMode', '')).lower() == 'external' for node in root.iter()): raise ValueError()
                if item.filename == '[Content_Types].xml':
                    expected = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' if ext == '.docx' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'
                    if not any(node.attrib.get('ContentType') == expected for node in root.iter()): raise ValueError()


async def scan_content(content):
    """No shell, filesystem execution, cloud upload or permissive scanner fallback."""
    host = os.environ.get('DOC_SCANNER_HOST', '').strip()
    if not host: raise HTTPException(503, 'Document scanning is not configured; upload was not saved')
    writer = None
    try:
        port = int(os.environ.get('DOC_SCANNER_PORT', '3310'))
        async with asyncio.timeout(60):
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(b'zINSTREAM\0')
            for start in range(0, len(content), 64 * 1024):
                chunk = content[start:start + 64 * 1024]
                writer.write(struct.pack('!I', len(chunk)) + chunk)
                await writer.drain()
            writer.write(struct.pack('!I', 0)); await writer.drain()
            response = await reader.readuntil(b'\0')
            if response == b'stream: OK\0': return
            if response.endswith(b' FOUND\0'): raise HTTPException(422, 'The document failed the malware scan')
            raise HTTPException(503, 'Document scanning could not confirm a clean result; upload was not saved')
    except HTTPException:
        raise
    except (OSError, ValueError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        raise HTTPException(503, 'Document scanning is unavailable; upload was not saved')
    finally:
        if writer:
            writer.close()
            try: await writer.wait_closed()
            except OSError: pass
