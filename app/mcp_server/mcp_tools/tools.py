import os
from mcp.server.fastmcp import FastMCP

import psycopg
from psycopg.rows import dict_row

import boto3

from mcp_tools.models import Park, ParkLookupResult


mcp = FastMCP("mcp", host="0.0.0.0", stateless_http=True)

async def connect():
    return await psycopg.AsyncConnection.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )

@mcp.tool()
async def find_parks_established_between(
    start_year: int,
    end_year: int,
) -> ParkLookupResult:
    """
    Return parks established within an inclusive year range.
    """
    if start_year > end_year:
        raise ValueError("start_year cannot be greater than end_year")

    if start_year < 1872 or end_year > 2100:
        raise ValueError("year range must be between 1872 and 2100")

    async with await connect() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT
                    park_code,
                    name,
                    state_code,
                    established_year
                FROM public.parks
                WHERE established_year BETWEEN %s AND %s
                ORDER BY established_year, name
                """,
                (start_year, end_year),
            )
            rows = await cursor.fetchall()

    parks = [Park.model_validate(row) for row in rows]
    return ParkLookupResult(parks=parks, count=len(parks))

@mcp.tool()
async def find_oldest_parks(limit: int = 5) -> ParkLookupResult:
    """
    Return parks ordered from earliest to most recently established.
    """
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    async with await connect() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT
                    park_code,
                    name,
                    state_code,
                    established_year
                FROM public.parks
                ORDER BY established_year, name
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cursor.fetchall()

    parks = [Park.model_validate(row) for row in rows]
    return ParkLookupResult(parks=parks, count=len(parks))

@mcp.tool()
async def find_park_by_code(park_code: str) -> ParkLookupResult:
    """
    Return the park associated with an exact four-character park code.
    """
    normalized_code = park_code.strip().lower()

    if len(normalized_code) != 4:
        raise ValueError("park_code must contain exactly four characters")

    async with await connect() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT
                    park_code,
                    name,
                    state_code,
                    established_year
                FROM public.parks
                WHERE park_code = %s
                """,
                (normalized_code,),
            )
            rows = await cursor.fetchall()

    parks = [Park.model_validate(row) for row in rows]
    return ParkLookupResult(parks=parks, count=len(parks))

@mcp.tool()
async def find_parks_in_state(state_code: str) -> ParkLookupResult:
    """
    Find parks within a state using state_code.
    """
    async with await connect() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                    SELECT * FROM public.parks
                    WHERE state_code = %s
                    ORDER BY name
                """,
                (state_code,)
            )
            rows = await cursor.fetchall()
    parks = [Park.model_validate(row) for row in rows]
    return ParkLookupResult(parks=parks, count=len(parks))

@mcp.tool()
async def find_parks_by_name(name_query: str) -> ParkLookupResult:
    """
    Find parks using a full or partial human-readable name.

    Use this to resolve a name such as "Acadia" into its canonical park_code.
    """
    search_term = name_query.strip()

    if not search_term:
        raise ValueError("name_query must not be empty")

    async with await connect() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT
                    park_code,
                    name,
                    state_code,
                    established_year
                FROM public.parks
                WHERE
                    to_tsvector('simple', name)
                        @@ plainto_tsquery('simple', %s)
                    OR name ILIKE '%%' || %s || '%%'
                ORDER BY
                    CASE
                        WHEN lower(name) = lower(%s) THEN 0
                        ELSE 1
                    END,
                    name
                LIMIT 10
                """,
                (search_term, search_term, search_term),
            )
            rows = await cursor.fetchall()

    parks = [Park.model_validate(row) for row in rows]
    return ParkLookupResult(parks=parks, count=len(parks))

@mcp.tool()
async def get_all_parks() -> ParkLookupResult:
    """
    Returns all parks data within database 
    """
    async with await connect() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                    SELECT * FROM public.parks
                    ORDER BY name
                """
            )

            rows = await cursor.fetchall()

    parks = [Park.model_validate(row) for row in rows]
    return ParkLookupResult(parks=parks, count=len(parks))

@mcp.tool()
def search_all_park_context(query: str) -> dict:
    """
    Search semantic context across every park document.

    Use only when no particular park has been identified.
    """
    client = boto3.client(
        "bedrock-agent-runtime",
        region_name="us-east-1",
    )

    response = client.retrieve(
        knowledgeBaseId=os.environ["KNOWLEDGE_BASE_ID"],
        retrievalQuery={
            "text": query,
        },
        retrievalConfiguration={
            "managedSearchConfiguration": {
                "numberOfResults": 10,
            }
        },
    )

    return {
        "results": [
            {
                "text": result.get("content", {}).get("text", ""),
                "score": result.get("score"),
                "location": result.get("location", {}),
                "metadata": result.get("metadata", {}),
            }
            for result in response.get("retrievalResults", [])
        ]
    }

@mcp.tool()
def retrieve_context(query: str, park_code:str) -> dict:
    """
    Search semantic context when a specific park has been identified by park code
    """
    client = boto3.client(
        "bedrock-agent-runtime",
        region_name="us-east-1" 
    )

    response = client.retrieve(
        knowledgeBaseId=os.environ["KNOWLEDGE_BASE_ID"],
        retrievalQuery={
            "text": query,
        },
        retrievalConfiguration={
            "managedSearchConfiguration": {
                "numberOfResults": 5,
                "filter": {
                    "equals": {
                        "key": "park_code",
                        "value": park_code.strip().lower()
                    }
                }
            }
        }
    )

    return {
        "park_code": park_code,
        "results": [
            {
                "text": result.get("content", {}).get("text", ""),
                "score": result.get("score"),
                "location": result.get("location", {}),
                "metadata": result.get("metadata", {})
            }
            for result in response.get("retrievalResults", [])
        ]
    }