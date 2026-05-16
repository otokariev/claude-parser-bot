import logging

import anthropic

from bot.config import settings

logger = logging.getLogger(__name__)

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# Model to use
MODEL = "claude-sonnet-4-5"

# System prompt — instructs Claude to answer only based on provided context
SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly based on the provided website content.

Rules:
- Answer ONLY based on the provided context from the website
- If the answer is not found in the context, say so clearly
- Do not use any external knowledge
- Be concise and precise
- Respond in the same language the user asked the question in
- Use HTML formatting for Telegram: <b>bold</b>, <i>italic</i>, <code>code</code>
- Do not use Markdown formatting (no *, **, _, __)"""


def ask_claude(question: str, context: str, url: str) -> str:
    """
    Send question and relevant context to Claude and get an answer.
    Claude will answer only based on the provided context.

    Args:
        question: User's question
        context: Relevant chunks from the website
        url: Source URL for reference

    Returns:
        Claude's answer as a string
    """
    try:
        prompt = f"""Website URL: {url}

Website content (relevant sections): {context}

User question: {question}

Please answer the question based only on the website content provided above."""

        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        answer = response.content[0].text
        logger.info(f"Claude answered question about {url}")
        return answer

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return f"Error getting answer from Claude: {str(e)}"


def ask_claude_for_clarification(question: str, url: str) -> str:
    """
    Ask Claude if the question needs clarification before searching.
    Returns clarifying question or empty string if no clarification needed.

    Args:
        question: User's question
        url: Source URL for context

    Returns:
        Clarifying question string or empty string
    """
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": f"""You are analyzing a user question about a website ({url}).

Question: "{question}"

Is this question too vague or ambiguous to search effectively? 
If yes — respond with ONE short clarifying question to help narrow down the search.
If no — respond with exactly: CLEAR

Respond with either the clarifying question or "CLEAR"."""
                }
            ],
        )

        result = response.content[0].text.strip()
        if result == "CLEAR":
            return ""
        return result

    except Exception as e:
        logger.error(f"Claude clarification error: {e}")
        return ""