"""
Adopted from VisualAgentBench https://github.com/THUDM/VisualAgentBench/blob/main/VAB-WebArena-Lite/new/evaluators.py
base class for evaluation
"""

# answer string match
import collections
import html
import importlib
import json
import logging
import urllib
from pathlib import Path
from typing import Union

from beartype import beartype
from nltk.tokenize import word_tokenize  # type: ignore
from playwright.sync_api import CDPSession, Page
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from .helper_functions import (
    PseudoPage,
    gitlab_get_project_memeber_role,
    llm_fuzzy_match,
    llm_ua_match,
    reddit_get_post_url,
    shopping_get_latest_order_url,
    shopping_get_sku_latest_review_author,
    shopping_get_sku_latest_review_rating,
)
from webarena.browser_env import Action, StateInfo

Trajectory = list[Union[Action, StateInfo]]

logger = logging.getLogger(__name__)

# bounds for waiting on the target page before evaluating locators
PAGE_LOAD_TIMEOUT_MS = 30_000
NETWORK_IDLE_TIMEOUT_MS = 5_000

# Playwright error messages that mean the page itself could not be evaluated
# (closed/crashed target, navigation race), as opposed to a locator that
# simply did not match anything on the page
_INFRASTRUCTURE_ERROR_MARKERS = (
    "Execution context was destroyed",
    "Cannot find context with specified id",
    "Target page, context or browser has been closed",
    "Target closed",
    "Browser has been closed",
    "Frame was detached",
    "Page crashed",
    "page is navigating",
)


class EvaluationInfrastructureError(RuntimeError):
    """The evaluator could not inspect the page, so no reward can be computed."""


def _is_infrastructure_error(error: BaseException) -> bool:
    if not isinstance(error, PlaywrightError):
        return False
    if isinstance(error, PlaywrightTimeoutError) or type(error).__name__ == "TargetClosedError":
        return True
    message = str(error)
    return any(marker in message for marker in _INFRASTRUCTURE_ERROR_MARKERS)


def _wait_for_page_ready(page: Page | PseudoPage) -> None:
    page.wait_for_load_state("load", timeout=PAGE_LOAD_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.debug(
            "Page %s did not reach networkidle within %d ms, evaluating anyway",
            page.url,
            NETWORK_IDLE_TIMEOUT_MS,
        )


def _query_page(page: Page | PseudoPage, query, description: str):
    """Run query(page), retrying once after the page settles on infrastructure errors.

    Raises EvaluationInfrastructureError if the page still cannot be queried, so
    that the failure is not mistaken for the agent failing the task. Other
    Playwright errors (e.g. a JS error because the locator matched nothing) are
    re-raised as-is for the caller to handle.
    """
    try:
        return query(page)
    except PlaywrightError as e:
        if not _is_infrastructure_error(e):
            raise
        logger.warning(
            "%s failed on %s with a page error, retrying once after the page settles: %r",
            description,
            page.url,
            e,
        )
    try:
        _wait_for_page_ready(page)
        return query(page)
    except PlaywrightError as e:
        if not _is_infrastructure_error(e):
            raise
        logger.error("%s failed on %s after retry: %r", description, page.url, e)
        raise EvaluationInfrastructureError(
            f"{description} could not be evaluated on {page.url}: {e!r}"
        ) from e


class Evaluator(object):
    def __init__(self, eval_tag: str = "") -> None:
        self.eval_tag = eval_tag

    @beartype
    def __call__(
        self,
        trajectory: Trajectory,
        config_file: Path | str,
        page: Page | PseudoPage,
        client: CDPSession,
    ) -> float:
        raise NotImplementedError

    @staticmethod
    def get_last_action(trajectory: Trajectory) -> "Action":
        try:
            # is_bearable(trajectory[-1], Action)
            last_action = trajectory[-1]
        except Exception:
            raise ValueError(
                "The last element of trajectory should be an action, add a fake stop action if needed"
            )

        return last_action  # type: ignore[return-value]

    @staticmethod
    def get_last_state(trajectory: Trajectory) -> "StateInfo":
        try:
            # is_bearable(trajectory[-2], StateInfo)
            last_state = trajectory[-2]
        except Exception:
            raise ValueError(
                "The second last element of trajectory should be a state, add a fake stop action if needed"
            )

        return last_state  # type: ignore[return-value]


class StringEvaluator(Evaluator):
    """Check whether the answer is correct with:
    exact match: the answer is exactly the same as the reference answer
    must include: each phrase in the reference answer must be included in the answer
    fuzzy match: the answer is similar to the reference answer, using LLM judge
    """

    @staticmethod
    @beartype
    def clean_answer(answer: str) -> str:
        answer = answer.strip()
        if answer.startswith("'") and answer.endswith("'"):
            answer = answer[1:-1]
        elif answer.startswith('"') and answer.endswith('"'):
            answer = answer[1:-1]
        return answer.lower()

    @staticmethod
    @beartype
    def exact_match(ref: str, pred: str) -> float:
        return float(StringEvaluator.clean_answer(pred) == StringEvaluator.clean_answer(ref))

    @staticmethod
    @beartype
    def must_include(ref: str, pred: str, tokenize: bool = False) -> float:
        clean_ref = StringEvaluator.clean_answer(ref)
        clean_pred = StringEvaluator.clean_answer(pred)
        # tokenize the answer if the ref is a single word
        # prevent false positive (e.g, 0)
        if tokenize and len(clean_ref) == 1 and len(word_tokenize(clean_ref)) == 1:
            tok_pred = word_tokenize(clean_pred)
            return float(clean_ref in tok_pred)
        else:
            return float(clean_ref in clean_pred)

    @staticmethod
    @beartype
    def fuzzy_match(ref: str, pred: str, intent: str) -> float:
        return llm_fuzzy_match(pred, ref, intent)

    @staticmethod
    @beartype
    def ua_match(ref: str, pred: str, intent: str) -> float:
        return llm_ua_match(pred, ref, intent)

    def __call__(
        self,
        trajectory: Trajectory,
        config_file: Path | str,
        page: Page | PseudoPage | None = None,
        client: CDPSession | None = None,
    ) -> float:
        with open(config_file, "r") as f:
            configs = json.load(f)

        last_action = self.get_last_action(trajectory)
        pred = self.clean_answer(last_action["answer"])

        score = 1.0
        for approach, value in configs["eval"]["reference_answers"].items():
            match approach:
                case "exact_match":
                    score *= self.exact_match(ref=value, pred=pred)

                case "must_include":
                    assert isinstance(value, list)
                    for must_value in value:
                        score *= self.must_include(
                            ref=must_value,
                            pred=pred,
                            tokenize=(len(value) == 1),
                        )
                case "fuzzy_match":
                    intent = configs["intent"]
                    if value == "N/A":
                        # if the instruction only asks the model to generate N/A when encountering an unachievable task
                        # without more concrete reasons
                        score *= self.exact_match(ref=value, pred=pred)
                        # if the instruction also asks the model to generate the reason why the task is unachievable
                        # this should be the default as it will prevent false positive N/A`
                        if score != 1:
                            score = 1.0 * self.ua_match(
                                intent=configs["intent"],
                                ref=configs["eval"]["string_note"],
                                pred=pred,
                            )
                    else:
                        assert isinstance(value, list)
                        for reference in value:
                            score *= self.fuzzy_match(ref=reference, pred=pred, intent=intent)
        return score


class URLEvaluator(Evaluator):
    """Check URL matching"""

    @beartype
    def __call__(
        self,
        trajectory: Trajectory,
        config_file: Path | str,
        page: Page | PseudoPage,
        client: CDPSession | None = None,
    ) -> float:
        with open(config_file, "r") as f:
            configs = json.load(f)

        def clean_url(url: str) -> str:
            url = str(url)
            url = url.rstrip("/")
            return url

        def parse_url(url: str) -> tuple[str, dict[str, list[str]]]:
            """Parse a URL into its base, path, and query components."""
            parsed_url = urllib.parse.urlparse(url)
            base_path = parsed_url.netloc + parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)
            return base_path, query

        def parse_urls(
            urls: list[str],
        ) -> tuple[list[str], dict[str, set[str]]]:
            """Parse a list of URLs."""
            base_paths = []
            queries = collections.defaultdict(set)
            for url in urls:
                base_path, query = parse_url(url)
                base_paths.append(base_path)
                for k, v in query.items():
                    queries[k].update(v)
            return base_paths, queries

        pred = clean_url(page.url)
        ref_urls = configs["eval"]["reference_url"].split(" |OR| ")
        ref_urls = [clean_url(url) for url in ref_urls]
        matching_rule = configs["eval"].get("url_note", "GOLD in PRED")
        if matching_rule == "GOLD in PRED":
            ref_base_paths, ref_queries = parse_urls(ref_urls)
            pred_base_paths, pred_query = parse_url(pred)

            base_score = float(
                any([ref_base_path in pred_base_paths for ref_base_path in ref_base_paths])
            )
            query_score = 1.0
            for k, possible_values in ref_queries.items():
                query_score *= float(
                    any(
                        possible_ref_value in pred_query.get(k, [])
                        for possible_ref_value in possible_values
                    )
                )
            score = base_score * query_score

        else:
            raise ValueError(f"Unknown matching rule: {matching_rule}")

        return score


class HTMLContentEvaluator(Evaluator):
    """Check whether the contents appear in the page"""

    """Check whether the contents appear in the page"""

    @staticmethod
    @beartype
    def fuzzy_match(ref: str, pred: str, intent: str) -> float:
        return llm_fuzzy_match(pred, ref, intent)

    def __call__(
        self,
        trajectory: Trajectory,
        config_file: Path | str,
        page: Page | PseudoPage,
        client: CDPSession | None = None,
    ) -> float:
        with open(config_file, "r") as f:
            configs = json.load(f)

        targets = configs["eval"]["program_html"]

        score = 1.0
        for target in targets:
            target_url: str = target["url"]  # which url to check
            if target_url.startswith("func"):
                func = target_url.split("func:")[1]
                func = func.replace("__last_url__", page.url)
                target_url = eval(func)

            locator: str = target["locator"]  # js element locator

            # navigate to that url
            if target_url != "last":
                page.goto(target_url)
                _wait_for_page_ready(page)

            # empty, use the full page
            if not locator.strip():
                selected_element = _query_page(
                    page, lambda p: p.content(), "HTMLContentEvaluator page.content()"
                )
            # use JS to select the element
            elif locator.startswith("document.") or locator.startswith("[...document."):
                if "prep_actions" in target:
                    try:
                        for prep_action in target["prep_actions"]:
                            _query_page(
                                page,
                                lambda p: p.evaluate(f"() => {prep_action}"),
                                f"HTMLContentEvaluator prep_action {prep_action!r}",
                            )
                    except PlaywrightError as e:
                        logger.warning(
                            "HTMLContentEvaluator prep_action %r raised on %s, skipping remaining prep_actions: %r",
                            prep_action,
                            page.url,
                            e,
                        )
                try:
                    selected_element = str(
                        _query_page(
                            page,
                            lambda p: p.evaluate(f"() => {locator}"),
                            f"HTMLContentEvaluator locator {locator!r}",
                        )
                    )
                    if not selected_element:
                        selected_element = ""
                except PlaywrightError as e:
                    # the locator did not match on this page, return empty
                    logger.warning(
                        "HTMLContentEvaluator locator %r raised on %s, using empty content: %r",
                        locator,
                        page.url,
                        e,
                    )
                    selected_element = ""
            elif locator.startswith("lambda:"):
                locator = locator[len("lambda:") :]
                try:
                    selected_element = _query_page(
                        page,
                        lambda p: p.evaluate(locator),
                        f"HTMLContentEvaluator locator {locator!r}",
                    )
                    if not selected_element:
                        selected_element = None
                except PlaywrightError as e:
                    # the locator did not match on this page, return empty
                    logger.warning(
                        "HTMLContentEvaluator locator %r raised on %s, using no content: %r",
                        locator,
                        page.url,
                        e,
                    )
                    selected_element = None
            # run program to call API
            elif locator.startswith("func:"):  # a helper function
                func = locator.split("func:")[1]
                func = func.replace("__page__", "page")
                selected_element = eval(func)
            else:
                raise ValueError(f"Unknown locator: {locator}")

            # If the selected element is None, then the page is wrong
            if selected_element is None:
                score = 0.0
                break

            if "exact_match" in target["required_contents"]:
                required_contents = target["required_contents"]["exact_match"]
                score *= StringEvaluator.exact_match(ref=required_contents, pred=selected_element)
            elif "must_include" in target["required_contents"]:
                required_contents = target["required_contents"]["must_include"]
                assert isinstance(required_contents, list)
                for content in required_contents:
                    content_or = content.split(" |OR| ")
                    score *= any(
                        [
                            StringEvaluator.must_include(ref=content, pred=selected_element)
                            for content in content_or
                        ]
                    )
            elif "fuzzy_match" in target["required_contents"]:
                required_contents = target["required_contents"]["fuzzy_match"]
                intent = configs["intent"]

                assert isinstance(required_contents, list)
                reference = ", ".join(required_contents)
                score *= self.fuzzy_match(ref=reference, pred=selected_element, intent=intent)
            else:
                raise ValueError(f"Unknown required_contents: {target['required_contents'].keys()}")

        return score


class EvaluatorComb:
    def __init__(self, evaluators: list[Evaluator]) -> None:
        self.evaluators = evaluators

    @beartype
    def __call__(
        self,
        trajectory: Trajectory,
        config_file: Path | str,
        page: Page | PseudoPage,
        client: CDPSession | None = None,
    ) -> float:
        score = 1.0
        for evaluator in self.evaluators:
            cur_score = evaluator(trajectory, config_file, page, client)
            score *= cur_score
        return score


@beartype
def evaluator_router(config_file: Path | str) -> EvaluatorComb:
    """Router to get the evaluator class"""
    with open(config_file, "r") as f:
        configs = json.load(f)

    eval_types = configs["eval"]["eval_types"]
    evaluators: list[Evaluator] = []
    for eval_type in eval_types:
        match eval_type:
            case "string_match":
                evaluators.append(StringEvaluator())
            case "url_match":
                evaluators.append(URLEvaluator())
            case "program_html":
                evaluators.append(HTMLContentEvaluator())
            case _:
                raise ValueError(f"eval_type {eval_type} is not supported")

    return EvaluatorComb(evaluators)
