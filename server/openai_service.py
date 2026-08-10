from urllib.parse import urlparse, urlunparse


def azure_openai_is_configured(settings: dict[str, str]) -> bool:
    required_settings = [
        settings["endpoint"],
        settings["api_key"],
        settings["deployment"],
    ]
    if settings["openai_endpoint_type"] == "azure_openai":
        required_settings.append(settings["api_version"])
    return all(required_settings)


def endpoint_uses_openai_compatible_client(endpoint: str) -> bool:
    normalized_endpoint = endpoint.lower().rstrip("/")
    return (
        "services.ai.azure.com" in normalized_endpoint
        or normalized_endpoint.endswith("/openai/v1")
    )


def build_openai_compatible_base_url(endpoint: str) -> str:
    normalized_endpoint = endpoint.strip().rstrip("/")
    parsed_endpoint = urlparse(normalized_endpoint)
    hostname = parsed_endpoint.netloc

    if hostname.endswith(".services.ai.azure.com"):
        hostname = hostname.removesuffix(".services.ai.azure.com")
        hostname = f"{hostname}.openai.azure.com"
        return urlunparse((parsed_endpoint.scheme, hostname, "/openai/v1", "", "", ""))

    if normalized_endpoint.lower().endswith("/openai/v1"):
        return normalized_endpoint

    return urlunparse(
        (parsed_endpoint.scheme, parsed_endpoint.netloc, "/openai/v1", "", "", "")
    )


def create_openai_chat_completion(
    settings: dict[str, str],
    messages: list[dict[str, str]],
    *,
    response_format: dict[str, str] | None = None,
    temperature: float | None = None,
    max_tokens: int = 350,
    timeout_seconds: float = 12.0,
):
    request_options = {
        "model": settings["deployment"],
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }
    if temperature is not None:
        request_options["temperature"] = temperature
    if response_format:
        request_options["response_format"] = response_format

    if endpoint_uses_openai_compatible_client(settings["endpoint"]):
        from openai import OpenAI

        client = OpenAI(
            api_key=settings["api_key"],
            base_url=build_openai_compatible_base_url(settings["endpoint"]),
            timeout=timeout_seconds,
        )
        return client.chat.completions.create(**request_options)

    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=settings["api_key"],
        azure_endpoint=settings["endpoint"],
        api_version=settings["api_version"],
        timeout=timeout_seconds,
    )
    return client.chat.completions.create(**request_options)


def format_openai_error(exc: Exception, settings: dict[str, str]) -> str:
    message = str(exc)
    for sensitive_value in (
        settings.get("api_key"),
        settings.get("endpoint"),
        settings.get("foundry_base_url"),
    ):
        if sensitive_value:
            message = message.replace(sensitive_value, "[redacted]")
    return f"Azure OpenAI request failed: {message}"
