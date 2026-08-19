#!/usr/bin/env python3
"""Generate an AIP coach password hash without echoing the password."""

from getpass import getpass

from aip.auth import password_hash


def main() -> None:
    first = getpass("Coach password: ")
    second = getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    print(password_hash(first))


if __name__ == "__main__":
    main()
