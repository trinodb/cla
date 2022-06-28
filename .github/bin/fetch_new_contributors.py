#!/usr/bin/env python

import argparse
import json
import logging
import sys
import unittest

from collections import OrderedDict
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# The ID and range of a sample spreadsheet.
SPREADSHEET_ID = '1oj5pnThQeQhSsQ80wJIz_sqGRZ4JZGlFQJtC9Ra9p00'
RANGE_NAME = 'Form Responses 1!G2:G'


def main():
    parser = argparse.ArgumentParser(
        description="Filter new contributors from Google Sheet with CLA responses."
    )
    parser.add_argument(
        "-c",
        "--contributors",
        type=argparse.FileType("r"),
        default="contributors",
        help="JSON file with current contributors",
    )
    parser.add_argument(
        "-a",
        "--account",
        type=argparse.FileType("r"),
        default="service-account.json",
        help="JSON file with service account credentials for Google Sheets",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="Filename to write a JSON array with new contributors to",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
        help="Print info level logs",
    )
    parser.add_argument(
        "-t",
        "--test",
        action='store_true',
        help="test this script instead of executing it",
    )

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    if args.test:
        sys.argv = [sys.argv[0]]
        unittest.main()
        return
    fetch_new_contributors(args.contributors, args.account, args.output)


def fetch_new_contributors(contributors_file, account_file, output_file):
    contributors = json.load(contributors_file)
    logging.debug("Existing contributors: %s", contributors)
    account_info = json.load(account_file)

    creds = Credentials.from_service_account_info(account_info, scopes=SCOPES)

    try:
        service = build('sheets', 'v4', credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])
        logging.debug("Sheet values: %s", values)

        new_contributors = find_new_contributors(contributors, values)
        logging.info("New contributors: %s", new_contributors)

        json.dump(new_contributors, output_file)
        output_file.write("\n")

    except HttpError:
        logging.exception("Exception caught while contacting a HTTP endpoint")


def find_new_contributors(contributors, sheet_values):
    flattened = [c for row in sheet_values for c in row[0].split(', ')]
    contributor_ids = list(OrderedDict.fromkeys([c[1:] if c[0] == "@" else c for c in flattened]))
    new_contributors = [c for c in contributor_ids if c not in contributors]
    return new_contributors


class TestBuild(unittest.TestCase):
    def test_find(self):
        cases = [
            # basic test
            (
                ["a", "b", "c"],
                [],
                []
            ),
            # Signup of existing contributor is ignored
            (
                ["a", "b", "c"],
                [["a"], ["@a"], ["a, @b"]],   # Testing all possible forms and multi-author entry splitting
                []
            ),
            # Signup of new contributors is returned
            (
                ["a", "b", "c"],
                [["d"], ["@d"], ["c, @c, d, @e"]],   # Testing all possible forms and multi-author entry splitting
                ["d", "e"]
            )
        ]
        for contributors, sheet_values, expected in cases:
            with self.subTest():
                output = find_new_contributors(contributors, sheet_values)
                self.assertListEqual(output, expected)


if __name__ == '__main__':
    main()
