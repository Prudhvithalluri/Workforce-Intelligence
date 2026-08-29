import asyncio
import json
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

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
logger.info("PROVIDER: AWS BEDROCK")
logger.info("==================================================")


# =========================================================
# BEDROCK CLIENT
# =========================================================

def _create_bedrock_client():

    logger.info("Creating AWS Bedrock Runtime client")

    logger.info(
        "AWS_REGION=%s",
        settings.AWS_REGION,
    )

    logger.info(
        "AWS_ACCESS_KEY_ID configured=%s",
        bool(settings.AWS_ACCESS_KEY_ID.strip()),
    )

    logger.info(
        "AWS_SECRET_ACCESS_KEY configured=%s",
        bool(settings.AWS_SECRET_ACCESS_KEY.strip()),
    )

    logger.info(
        "AWS_SESSION_TOKEN configured=%s",
        bool(settings.AWS_SESSION_TOKEN.strip()),
    )

    client_kwargs = {
        "service_name": "bedrock-runtime",
        "region_name": settings.AWS_REGION,
    }

    if settings.AWS_ACCESS_KEY_ID.strip():

        client_kwargs["aws_access_key_id"] = (
            settings.AWS_ACCESS_KEY_ID
        )

    if settings.AWS_SECRET_ACCESS_KEY.strip():

        client_kwargs["aws_secret_access_key"] = (
            settings.AWS_SECRET_ACCESS_KEY
        )

    if settings.AWS_SESSION_TOKEN.strip():

        client_kwargs["aws_session_token"] = (
            settings.AWS_SESSION_TOKEN
        )

    client = boto3.client(
        **client_kwargs
    )

    logger.info(
        "AWS Bedrock Runtime client created successfully"
    )

    return client


bedrock_client = _create_bedrock_client()


# =========================================================
# BEDROCK INVOCATION
# =========================================================

def _invoke_bedrock(messages: list[dict]) -> str:

    logger.info("--------------------------------------------------")
    logger.info("BEDROCK INVOCATION START")
    logger.info("--------------------------------------------------")

    model_id = (
        settings.BEDROCK_MODEL_ID.strip()
    )

    logger.info(
        "BEDROCK_MODEL_ID=%s",
        model_id,
    )

    logger.info(
        "AWS_REGION=%s",
        settings.AWS_REGION,
    )

    if not model_id:

        logger.error(
            "BEDROCK_MODEL_ID is EMPTY"
        )

        raise RuntimeError(
            "BEDROCK_MODEL_ID is empty. "
            "Add your Bedrock model ID to backend/.env."
        )

    logger.info(
        "Number of messages: %d",
        len(messages),
    )

    # -----------------------------------------------------
    # Build messages
    # -----------------------------------------------------

    system_messages = []

    user_messages = []

    for message in messages:

        role = message.get(
            "role"
        )

        content = message.get(
            "content",
            "",
        )

        logger.debug(
            "Message role=%s content_length=%d",
            role,
            len(content),
        )

        if role == "system":

            system_messages.append(
                {
                    "text": content
                }
            )

        elif role == "user":

            user_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "text": content
                        }
                    ],
                }
            )

        elif role == "assistant":

            user_messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {
                            "text": content
                        }
                    ],
                }
            )

    # -----------------------------------------------------
    # Bedrock request
    # -----------------------------------------------------

    request = {
        "modelId": model_id,

        "messages": user_messages,

        "inferenceConfig": {
            "temperature": 0,
            "maxTokens": 1000,
        },
    }

    if system_messages:

        request["system"] = system_messages

    logger.info(
        "Calling bedrock_client.converse()"
    )

    logger.debug(
        "Bedrock request modelId=%s",
        model_id,
    )

    try:

        response = (
            bedrock_client.converse(
                **request
            )
        )

    except ClientError as exc:

        logger.exception(
            "AWS ClientError while calling Bedrock"
        )

        raise RuntimeError(
            "AWS Bedrock ClientError: "
            f"{exc}"
        ) from exc

    except BotoCoreError as exc:

        logger.exception(
            "AWS BotoCoreError while calling Bedrock"
        )

        raise RuntimeError(
            "AWS Bedrock BotoCoreError: "
            f"{exc}"
        ) from exc

    except Exception as exc:

        logger.exception(
            "Unexpected error while calling Bedrock"
        )

        raise RuntimeError(
            "Unexpected Bedrock error: "
            f"{exc}"
        ) from exc

    logger.info(
        "Bedrock response received successfully"
    )

    # -----------------------------------------------------
    # Extract output
    # -----------------------------------------------------

    try:

        output = (
            response[
                "output"
            ][
                "message"
            ][
                "content"
            ]
        )

    except (
        KeyError,
        TypeError,
    ) as exc:

        logger.exception(
            "Could not extract text from Bedrock response"
        )

        raise RuntimeError(
            "Unexpected response received "
            "from AWS Bedrock."
        ) from exc

    text_parts = []

    for item in output:

        if "text" in item:

            text_parts.append(
                item["text"]
            )

    content = "".join(
        text_parts
    ).strip()

    logger.info(
        "Bedrock response text length=%d",
        len(content),
    )

    logger.debug(
        "Bedrock response received length=%d",
        len(content),
    )

    if not content:

        logger.error(
            "Bedrock returned EMPTY response"
        )

        raise RuntimeError(
            "AWS Bedrock returned an empty response."
        )

    logger.info(
        "BEDROCK INVOCATION END"
    )

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

    logger.info(
        "Provider: AWS BEDROCK"
    )

    logger.info(
        "Region: %s",
        settings.AWS_REGION,
    )

    logger.info(
        "Model ID: %s",
        settings.BEDROCK_MODEL_ID,
    )

    logger.info(
        "Available actions: %s",
        available_actions,
    )

    if not settings.AWS_REGION.strip():

        logger.error(
            "AWS_REGION is empty"
        )

        raise RuntimeError(
            "AWS_REGION is empty."
        )

    if not settings.BEDROCK_MODEL_ID.strip():

        logger.error(
            "BEDROCK_MODEL_ID is empty"
        )

        raise RuntimeError(
            "BEDROCK_MODEL_ID is empty."
        )

    # -----------------------------------------------------
    # Current state
    # -----------------------------------------------------

    payload = {

        "operation": context.get(
            "operation"
        ),

        "current_step": context.get(
            "current_step"
        ),

        # Location is deliberately NOT sent to the LLM.
        # It is frontend-supplied workflow data used only by Python/Playwright.

        "last_verified_step": context.get(
            "last_verified_step"
        ),

        "retry_count": context.get(
            "retry_count",
            0,
        ),

        "page_url": context.get(
            "page_url"
        ),

        "page_title": context.get(
            "page_title"
        ),

        "checks": context.get(
            "checks",
            {},
        ),

        "last_action": context.get(
            "action"
        ),

        "last_action_result": context.get(
            "action_result"
        ),

        "error": context.get(
            "error"
        ),

        "recovery_reason": context.get(
            "recovery_reason"
        ),
        "failed_action": context.get("failed_action"),

        "failed_step": context.get("failed_step"),

        "recovery_checks": context.get("recovery_checks", {}),
    }

    logger.info(
        "Current operation=%s",
        payload["operation"],
    )

    logger.info(
        "Current step=%s",
        payload["current_step"],
    )

    logger.info(
        "Last verified step=%s",
        payload["last_verified_step"],
    )

    logger.info(
        "Retry count=%s",
        payload["retry_count"],
    )

    logger.info(
        "Page URL=%s",
        payload["page_url"],
    )

    if payload["error"]:

        logger.warning(
            "Workflow error=%s",
            payload["error"],
        )

    # -----------------------------------------------------
    # Build prompt
    # -----------------------------------------------------

    user_content = (
        action_schema(
            available_actions
        )
        + "\nCURRENT STATE:\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
        )
    )

    messages = [

        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },

        {
            "role": "user",
            "content": user_content,
        },

    ]

    logger.info(
        "LLM prompt prepared"
    )

    # -----------------------------------------------------
    # Call Bedrock
    # -----------------------------------------------------

    logger.info(
        "Sending request to AWS Bedrock..."
    )

    content = await asyncio.to_thread(
        _invoke_bedrock,
        messages,
    )

    logger.info(
        "AWS Bedrock returned successfully"
    )

    # -----------------------------------------------------
    # Clean response
    # -----------------------------------------------------

    cleaned_content = (
        content.strip()
    )

    if cleaned_content.startswith(
        "```"
    ):

        logger.debug(
            "Removing markdown code fence from response"
        )

        cleaned_content = (
            cleaned_content
            .replace(
                "```json",
                "",
                1,
            )
            .replace(
                "```",
                "",
            )
            .strip()
        )

    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------

    try:

        result = json.loads(
            cleaned_content
        )

    except json.JSONDecodeError as exc:

        logger.error(
            "Invalid JSON returned by Bedrock"
        )

        logger.error("Bedrock response parsing failed length=%d", len(content))

        raise ValueError(
            "AWS Bedrock returned invalid JSON: "
            f"{content}"
        ) from exc

    # -----------------------------------------------------
    # Validate result
    # -----------------------------------------------------

    if not isinstance(
        result,
        dict,
    ):

        logger.error(
            "Bedrock result is not a JSON object"
        )

        raise ValueError(
            "AWS Bedrock response must be a JSON object."
        )

    action = result.get(
        "action"
    )

    logger.info(
        "LLM SELECTED ACTION: %s",
        action,
    )

    # -----------------------------------------------------
    # Validate action
    # -----------------------------------------------------

    if action not in available_actions:

        logger.error(
            "LLM selected an action outside the allowed step: %s",
            action,
        )
        logger.error(
            "Allowed actions for this step: %s",
            available_actions,
        )

        # The candidate list is enforced by Python. If the model violates the
        # contract, never execute the invalid action. When exactly one action
        # is legal, it is unambiguous and safe to continue with that action.
        # This prevents a model formatting/selection error from breaking a
        # deterministic browser step such as app_authenticated -> open_site.
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
            "LLM selected invalid action: "
            f"{action}. Available actions: {available_actions}"
        )

    logger.info(
        "Valid LLM action selected: %s",
        action,
    )

    logger.info(
        "CHOOSE_ACTION COMPLETE"
    )

    return result