"""Operator CLI: passwords are read from a hidden prompt, never command arguments."""
import argparse
from getpass import getpass
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User
from app.security import DEMO_USERS, hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "set-password", "deactivate", "deactivate-demo"])
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--company")
    parser.add_argument("--role", choices=["buyer", "supplier"])
    args = parser.parse_args()
    if args.action != "deactivate-demo" and not args.email:
        parser.error("--email is required")
    with SessionLocal() as db:
        if args.action == "deactivate-demo":
            users = list(db.scalars(select(User).where(User.email.in_([u.email for u in DEMO_USERS]))))
        else:
            user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if args.action == "create":
                if user or not all([args.name, args.company, args.role]):
                    parser.error("Use a new email and provide --name, --company and --role")
                user = User(email=args.email.strip().lower(), name=args.name, company_name=args.company, role=args.role, token_version=0)
                db.add(user)
            elif not user:
                parser.error("User not found")
            users = [user]
        for user in users:
            user.token_version = (user.token_version or 0) + 1
            if args.action.startswith("deactivate"):
                user.is_active = False
            else:
                password = getpass("New password (12+ characters): ")
                if len(password) < 12 or password != getpass("Confirm password: "):
                    parser.error("Passwords must match and contain at least 12 characters")
                user.password_hash, user.password_salt = hash_password(password)
        db.commit()
        print(f"Updated {len(users)} account(s).")


if __name__ == "__main__":
    main()
