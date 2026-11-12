"""Errors whose messages are written for end users and safe to display."""
from __future__ import annotations


class UserError(Exception):
    status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(UserError):
    status = 404


class ConflictError(UserError):
    status = 409


class BusyError(UserError):
    status = 429


class TooLargeError(UserError):
    status = 413
