import asyncio
import json
import logging

from openai import AzureOpenAI, APIError, APIConnectionError

from config import settings
from agent.prompts import SYSTEM_PROMPT, action_schema


# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)


# =========================================================
# DEBUG STARTUP LOG
# =========================================================

logger.info("==================================================")
logger.info("LLM MODULE LOADED")
logger.info("PROVIDER: AZURE OPENAI")
logger.info("==================================================")


# =========================================================
# AZURE OPENAI CLIENT
# =========================================================

def _create_azure_client() -> AzureOpenAI:

    logger.info("Creating Azure OpenAI client")

    logger.info(
        "AZURE_OPENAI_ENDPOINT=%s",
        settings.AZURE_OPENAI_ENDPOINT,
    )

    logger.info(
        "AZURE_OPENAI_API_KEY configured=%s",
        bool(settings.AZURE_OPENAI_API_KEY.strip()),
    )

    logger.info(
        "AZURE_OPENAI_API_VERSION=%s",
        settings.AZURE_OPENAI_API_VERSION,
    )

    if not settings.AZURE_OPENAI_API_KEY.strip():
        raise RuntimeError(
            "AZURE_OPENAI_API_KEY is empty. Add it to backend/.env."
        )

    if not settings.AZURE_OPENAI_ENDPOINT.strip():
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT is empty. Add it to backend/.env."
        )

    client = AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version=settings.AZURE_OPENAI_API_VERSION,
    )

    logger.info("Azure OpenAI client created successfully")

    return client


azure_client = _create_azure_client()


# =========================================================
# AZURE OPENAI INVOCATION
# =========================================================

def _invoke_azure_openai(messages: list[dict]) -> str:

    logger.info("--------------------------------------------------")
    logger.info("AZURE OPENAI INVOCATION START")
    logger.info("--------------------------------------------------")

    deployment = settings.AZURE_OPENAI_DEPLOYMENT.strip()

    logger.info("AZURE_OPENAI_DEPLOYMENT=%s", deployment)

    if not deployment:
        logger.error("AZURE_OPENAI_DEPLOYMENT is EMPTY")
        raise RuntimeError(
            "AZURE_OPENAI_DEPLOYMENT is empty. "
            "Add your Azure OpenAI deployment name to backend/.env."
        )

    logger.info("Number of messages: %d", len(messages))

    # Azure OpenAI's chat completions API takes the same
    # {"role": ..., "content": ...} shape already used by "messages" here,
    # so no reshaping is needed (unlike the Bedrock converse() format).
    for message in messages:
        logger.debug(
            "Message role=%s content_length=%d",
            message.get("role"),
            len(message.get("content", "")),
        )

    logger.info("Calling azure_client.chat.completions.create()")

    try:
        response = azure_client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=0,
            max_tokens=1000,
        )

    except APIConnectionError as exc:
        logger.exception("Azure OpenAI connection error")
        raise RuntimeError(
            f"Azure OpenAI connection error: {exc}"
        ) from exc

    except APIError as exc:
        logger.exception("Azure OpenAI API error")
        raise RuntimeError(
            f"Azure OpenAI API error: {exc}"
        ) from exc

    except Exception as exc:
        logger.exception("Unexpected error while calling Azure OpenAI")
        raise RuntimeError(
            f"Unexpected Azure OpenAI error: {exc}"
        ) from exc

    logger.info("Azure OpenAI response received successfully")

    # -----------------------------------------------------
    # Extract output
    # -----------------------------------------------------

    try:
        content = response.choices[0].message.content or ""
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        logger.exception("Could not extract text from Azure OpenAI response")
        raise RuntimeError(
            "Unexpected response received from Azure OpenAI."
        ) from exc

    content = content.strip()

    logger.info("Azure OpenAI response text length=%d", len(content))

    if not content:
        logger.error("Azure OpenAI returned EMPTY response")
        raise RuntimeError("Azure OpenAI returned an empty response.")

    logger.info("AZURE OPENAI INVOCATION END")

    return content


# =========================================================
# CHOOSE ACTION
# =========================================================

async def choose_action(
    context: dict,
    available_actions: list[str],
) -> dict:

    logger.info("")
    logger.info("==================================================")
    logger.info("CHOOSE_ACTION CALLED")
    logger.info("==================================================")

    # -----------------------------------------------------
    # Configuration
    # -----------------------------------------------------

    logger.info("Provider: AZURE OPENAI")
    logger.info("Endpoint: %s", settings.AZURE_OPENAI_ENDPOINT)
    logger.info("Deployment: %s", settings.AZURE_OPENAI_DEPLOYMENT)
    logger.info("Available actions: %s", available_actions)

    if not settings.AZURE_OPENAI_ENDPOINT.strip():
        logger.error("AZURE_OPENAI_ENDPOINT is empty")
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is empty.")

    if not settings.AZURE_OPENAI_DEPLOYMENT.strip():
        logger.error("AZURE_OPENAI_DEPLOYMENT is empty")
        raise RuntimeError("AZURE_OPENAI_DEPLOYMENT is empty.")

    # -----------------------------------------------------
    # Current state
    # -----------------------------------------------------

    payload = {
        "operation": context.get("operation"),
        "current_step": context.get("current_step"),
        # Location is deliberately NOT sent to the LLM.
        # It is frontend-supplied workflow data used only by Python/Playwright.
        "last_verified_step": context.get("last_verified_step"),
        "retry_count": context.get("retry_count", 0),
        "page_url": context.get("page_url"),
        "page_title": context.get("page_title"),
        "checks": context.get("checks", {}),
        "last_action": context.get("action"),
        "last_action_result": context.get("action_result"),
        "error": context.get("error"),
        "recovery_reason": context.get("recovery_reason"),
        "failed_action": context.get("failed_action"),
        "failed_step": context.get("failed_step"),
        "recovery_checks": context.get("recovery_checks", {}),
    }

    logger.info("Current operation=%s", payload["operation"])
    logger.info("Current step=%s", payload["current_step"])
    logger.info("Last verified step=%s", payload["last_verified_step"])
    logger.info("Retry count=%s", payload["retry_count"])
    logger.info("Page URL=%s", payload["page_url"])

    if payload["error"]:
        logger.warning("Workflow error=%s", payload["error"])

    # -----------------------------------------------------
    # Build prompt
    # -----------------------------------------------------

    user_content = (
        action_schema(available_actions)
        + "\nCURRENT STATE:\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    logger.info("LLM prompt prepared")

    # -----------------------------------------------------
    # Call Azure OpenAI
    # -----------------------------------------------------

    logger.info("Sending request to Azure OpenAI...")

    content = await asyncio.to_thread(
        _invoke_azure_openai,
        messages,
    )

    logger.info("Azure OpenAI returned successfully")

    # -----------------------------------------------------
    # Clean response
    # -----------------------------------------------------

    cleaned_content = content.strip()

    if cleaned_content.startswith("```"):
        logger.debug("Removing markdown code fence from response")
        cleaned_content = (
            cleaned_content
            .replace("```json", "", 1)
            .replace("```", "")
            .strip()
        )

    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------

    try:
        result = json.loads(cleaned_content)

    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON returned by Azure OpenAI")
        logger.error("Azure OpenAI response parsing failed length=%d", len(content))
        raise ValueError(
            f"Azure OpenAI returned invalid JSON: {content}"
        ) from exc

    # -----------------------------------------------------
    # Validate result
    # -----------------------------------------------------

    if not isinstance(result, dict):
        logger.error("Azure OpenAI result is not a JSON object")
        raise ValueError("Azure OpenAI response must be a JSON object.")

    action = result.get("action")

    logger.info("LLM SELECTED ACTION: %s", action)

    # -----------------------------------------------------
    # Validate action
    # -----------------------------------------------------

    if action not in available_actions:
        logger.error(
            "LLM selected an action outside the allowed step: %s", action
        )
        logger.error("Allowed actions for this step: %s", available_actions)

        # The candidate list is enforced by Python. If the model violates the
        # contract, never execute the invalid action. When exactly one action
        # is legal, it is unambiguous and safe to continue with that action.
        if len(available_actions) == 1:
            fallback = available_actions[0]
            logger.warning(
                "LLM action rejected; using the only legal action: %s",
                fallback,
            )
            return {
                "action": fallback,
                "reason": (
                    "The model returned an invalid action; Python selected "
                    "the only legal action for the current step."
                ),
            }

        raise ValueError(
            f"LLM selected invalid action: {action}. "
            f"Available actions: {available_actions}"
        )

    logger.info("Valid LLM action selected: %s", action)
    logger.info("CHOOSE_ACTION COMPLETE")

    return result