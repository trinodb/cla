#!/usr/bin/env python

import argparse
import json
import logging
import os
import requests
import sys
import time
import unittest

SEARCH_API_URL = 'https://api.github.com/search/issues'

OWNER = "MiguelWeezardo"
REPO = "trino"
ISSUES_API_BASE_URL = 'https://api.github.com/repos/' + OWNER + "/" + REPO + "/issues"


def main():
    parser = argparse.ArgumentParser(
        description="Summon CLA-bot for all PRs by new contributors."
    )
    parser.add_argument(
        "-c",
        "--contributors",
        type=argparse.FileType("r"),
        default="new_contributors",
        help="JSON file with new contributors",
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
    summon_cla_bot(args.contributors)


def summon_cla_bot(contributors_file):
    contributors = json.load(contributors_file)
    logging.debug("Contributors: %s", contributors)
    if len(contributors) == 0:
        return
    pull_request_numbers = find_pulls_of_new_contributors(contributors, requests)
    logging.info("Posting '@cla-bot check' comment on pull requests: %s", pull_request_numbers)
    post_comment_on(pull_request_numbers, requests, time)


def find_pulls_of_new_contributors(contributors, req):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "token " + os.getenv("GITHUB_TOKEN")
    }
    query = " ".join(["type:pull-request", "repo:" + OWNER + "/" + REPO, "state:open", "-label:cla-signed"] + ["author:" + contributor for contributor in contributors])

    pr_numbers = []
    try:
        # The Search API Endpoint only allows up to 1000 results, hence the range has been set to 10 with 100 entries per page
        for page in range(1, 10):
            response = req.get(SEARCH_API_URL, headers=headers, params={"q": query, 'per_page': 100, 'page': page}).json()
            logging.info("Response from %s: %s", SEARCH_API_URL, response)
            new_pr_numbers = [pr["number"] for pr in response["items"]]
            logging.debug("New PR numbers: %s", new_pr_numbers)
            if len(new_pr_numbers) == 0:
                break
            pr_numbers = pr_numbers + new_pr_numbers
    except KeyError:
        logging.exception("Exception while parsing search response")
        raise

    return set(pr_numbers)


def post_comment_on(pull_request_numbers, requests_module, time_module):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "token " + os.getenv("GITHUB_TOKEN")
    }

    responses = []
    for pull_request_number in pull_request_numbers:
        time_module.sleep(1)
        pulls_api_url = ISSUES_API_BASE_URL + "/" + str(pull_request_number) + "/comments"
        response = requests_module.post(pulls_api_url, headers=headers, json={"body": "@cla-bot check"}).json()
        logging.debug("Response from %s: %s", pulls_api_url, response)
        responses.append(response)

    return responses

class FakeGetPullsResponse:
    def __init__(self, result):
        self.result = result

    def json(self):
        return {"items": [{"number": x} for x in self.result]}


class FakePostCommentResponse:
    def __init__(self, url):
        self.url = url

    def json(self):
        return {"url": self.url}


class FakeRequests:
    def __init__(self, get_results):
        self.get_results = get_results

    def get(self, url, params=None, **kwargs):
        try:
            logging.debug("FakeRequests.get(url=%s, params=%s, kwargs= %s)", url, params, kwargs)
            return FakeGetPullsResponse(self.get_results.pop(0))
        except IndexError:
            return FakeGetPullsResponse([])

    def post(self, url, data=None, json=None, **kwargs):
        logging.debug("FakeRequests.post(url=%s, data=%s, json=%s, kwargs=%s)", url, data, json, kwargs)
        return FakePostCommentResponse(url)


class FakeTime:
    def sleep(self, seconds):
        pass


class TestBuild(unittest.TestCase):
    def test_find(self):
        cases = [
            # Empty results
            (
                ["a", "b", "c"],
                [],
                set([])
            ),
            # Single page is returned, with duplicates removed
            (
                ["a", "b", "c"],
                [[1, 2, 3, 3, 3]],
                set([1, 2, 3])
            ),
            # Multiple pages are merged, and duplicates removed
            (
                ["a", "b", "c"],
                [[1, 2, 3, 4], [4, 5, 6, 7], [6, 7, 8, 9]],
                set([1, 2, 3, 4, 5, 6, 7, 8, 9])
            )
        ]
        for contributors, search_results, expected in cases:
            with self.subTest():
                output = find_pulls_of_new_contributors(contributors, FakeRequests(search_results))
                self.assertSetEqual(output, expected)

    def test_post(self):
        cases = [
            # Empty results
            (
                set([])
            ),
            # Single pull request comment
            (
                set([1])
            ),
            # Multiple pull request comments
            (
                set([1, 2, 3])
            )
        ]
        for pull_request_numbers in cases:
            with self.subTest():
                output = post_comment_on(pull_request_numbers, FakeRequests([]), FakeTime())
                self.assertListEqual(output, [{"url": ISSUES_API_BASE_URL + "/" + str(pr) + "/comments"} for pr in pull_request_numbers])


if __name__ == '__main__':
    main()
