"""Reminder Service — centralised scheduled reminder runner.

The Reminder Service is a separate component from the Notification Service.
It runs jobs on a cron schedule, evaluates conditions against MongoDB, and
fires reminder events into the Notification Service via the email_triggers
helper. The Notification Service handles template resolution and dispatch.
"""
