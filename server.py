#!/usr/bin/env python
import os
import sys
import json
import datetime
from typing import Optional

try:
    from fast_flights import FlightData, Passengers, get_flights
except ImportError as e:
    print(f"Error importing fast_flights: {e}", file=sys.stderr)
    sys.exit(1)

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "google-flights-cheapest-finder",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


# --- Helpers ---

def flight_to_dict(flight):
    return {
        "is_best": getattr(flight, "is_best", None),
        "name": getattr(flight, "name", None),
        "departure": getattr(flight, "departure", None),
        "arrival": getattr(flight, "arrival", None),
        "arrival_time_ahead": getattr(flight, "arrival_time_ahead", None),
        "duration": getattr(flight, "duration", None),
        "stops": getattr(flight, "stops", None),
        "delay": getattr(flight, "delay", None),
        "price": getattr(flight, "price", None),
    }


def parse_price(price_str):
    if not price_str or not isinstance(price_str, str):
        return float("inf")
    try:
        return int(price_str.replace("$", "").replace(",", ""))
    except ValueError:
        return float("inf")


# --- Tools ---

@mcp.tool()
async def get_flights_on_date(
    origin: str,
    destination: str,
    date: str,
    adults: int = 1,
    seat_type: str = "economy",
    return_cheapest_only: bool = False,
) -> str:
    """Fetches one-way flights for a specific date between two airports.

    Args:
        origin: Origin airport IATA code (e.g. "DEL").
        destination: Destination airport IATA code (e.g. "BOM").
        date: Travel date YYYY-MM-DD.
        adults: Number of adult passengers. Default 1.
        seat_type: "economy", "premium-economy", "business", or "first".
        return_cheapest_only: If True, return only the cheapest flight.
    """
    print(f"MCP Tool: get_flights_on_date {origin}->{destination} for {date}", file=sys.stderr)
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")

        result = get_flights(
            flight_data=[FlightData(date=date, from_airport=origin, to_airport=destination)],
            trip="one-way",
            seat=seat_type,
            passengers=Passengers(adults=adults),
        )

        if result and result.flights:
            if return_cheapest_only:
                cheapest = min(result.flights, key=lambda f: parse_price(f.price))
                payload = {"cheapest_flight": flight_to_dict(cheapest)}
            else:
                payload = {"flights": [flight_to_dict(f) for f in result.flights]}

            return json.dumps({
                "search_parameters": {
                    "origin": origin, "destination": destination, "date": date,
                    "adults": adults, "seat_type": seat_type,
                    "return_cheapest_only": return_cheapest_only,
                },
                **payload,
            }, indent=2)

        return json.dumps({
            "message": f"No flights found for {origin} -> {destination} on {date}.",
            "search_parameters": {
                "origin": origin, "destination": destination, "date": date,
                "adults": adults, "seat_type": seat_type,
            },
        })

    except ValueError:
        return json.dumps({"error": {"message": f"Invalid date format: '{date}'. Use YYYY-MM-DD.", "type": "ValueError"}})
    except Exception as e:
        print(f"MCP Tool Error in get_flights_on_date: {e}", file=sys.stderr)
        return json.dumps({"error": {"message": "An unexpected error occurred.", "type": type(e).__name__}})


@mcp.tool()
async def get_round_trip_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int = 1,
    seat_type: str = "economy",
    return_cheapest_only: bool = False,
) -> str:
    """Fetches round-trip flights for specific departure and return dates.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Outbound date YYYY-MM-DD.
        return_date: Return date YYYY-MM-DD.
        adults: Number of adult passengers. Default 1.
        seat_type: "economy", "premium-economy", "business", or "first".
        return_cheapest_only: If True, return only the cheapest flight.
    """
    print(f"MCP Tool: get_round_trip_flights {origin}<->{destination} {departure_date} to {return_date}", file=sys.stderr)
    try:
        datetime.datetime.strptime(departure_date, "%Y-%m-%d")
        datetime.datetime.strptime(return_date, "%Y-%m-%d")

        result = get_flights(
            flight_data=[
                FlightData(date=departure_date, from_airport=origin, to_airport=destination),
                FlightData(date=return_date, from_airport=destination, to_airport=origin),
            ],
            trip="round-trip",
            seat=seat_type,
            passengers=Passengers(adults=adults),
        )

        if result and result.flights:
            if return_cheapest_only:
                cheapest = min(result.flights, key=lambda f: parse_price(f.price))
                payload = {"cheapest_round_trip_option": flight_to_dict(cheapest)}
            else:
                payload = {"round_trip_options": [flight_to_dict(f) for f in result.flights]}

            return json.dumps({
                "search_parameters": {
                    "origin": origin, "destination": destination,
                    "departure_date": departure_date, "return_date": return_date,
                    "adults": adults, "seat_type": seat_type,
                    "return_cheapest_only": return_cheapest_only,
                },
                **payload,
            }, indent=2)

        return json.dumps({
            "message": f"No round-trip flights found for {origin} <-> {destination} from {departure_date} to {return_date}.",
            "search_parameters": {
                "origin": origin, "destination": destination,
                "departure_date": departure_date, "return_date": return_date,
                "adults": adults, "seat_type": seat_type,
            },
        })

    except ValueError:
        return json.dumps({"error": {"message": "Invalid date format. Use YYYY-MM-DD.", "type": "ValueError"}})
    except Exception as e:
        print(f"MCP Tool Error in get_round_trip_flights: {e}", file=sys.stderr)
        return json.dumps({"error": {"message": "An unexpected error occurred.", "type": type(e).__name__}})


@mcp.tool(name="find_all_flights_in_range")
async def find_all_flights_in_range(
    origin: str,
    destination: str,
    start_date_str: str,
    end_date_str: str,
    min_stay_days: Optional[int] = None,
    max_stay_days: Optional[int] = None,
    adults: int = 1,
    seat_type: str = "economy",
    return_cheapest_only: bool = False,
) -> str:
    """Finds round-trip flights for every valid departure/return pair in a date range.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        start_date_str: Start of search range YYYY-MM-DD.
        end_date_str: End of search range YYYY-MM-DD.
        min_stay_days: Minimum stay duration in days.
        max_stay_days: Maximum stay duration in days.
        adults: Number of adult passengers. Default 1.
        seat_type: "economy", "premium-economy", "business", or "first".
        return_cheapest_only: If True, return only the cheapest flight per date pair.
    """
    print(f"MCP Tool: find_all_flights_in_range {origin}<->{destination} {start_date_str} to {end_date_str}", file=sys.stderr)

    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        return json.dumps({"error": {"message": "Invalid date format. Use YYYY-MM-DD.", "type": "ValueError"}})

    if start_date > end_date:
        return json.dumps({"error": {"message": "Start date cannot be after end date.", "type": "ValueError"}})

    date_list = []
    cur = start_date
    while cur <= end_date:
        date_list.append(cur)
        cur += datetime.timedelta(days=1)

    pairs = []
    for i, dep in enumerate(date_list):
        for ret in date_list[i:]:
            stay = (ret - dep).days
            if min_stay_days is not None and stay < min_stay_days:
                continue
            if max_stay_days is not None and stay > max_stay_days:
                continue
            pairs.append((dep, ret))

    if not pairs:
        return json.dumps({"error": "No valid date pairs in range with the given constraints."})

    print(f"MCP Tool: checking {len(pairs)} date combinations", file=sys.stderr)

    results_data = []
    error_messages = []

    for idx, (dep, ret) in enumerate(pairs, 1):
        if idx % 10 == 0:
            print(f"MCP Tool Progress: {idx}/{len(pairs)}", file=sys.stderr)

        try:
            result = get_flights(
                flight_data=[
                    FlightData(date=dep.strftime("%Y-%m-%d"), from_airport=origin, to_airport=destination),
                    FlightData(date=ret.strftime("%Y-%m-%d"), from_airport=destination, to_airport=origin),
                ],
                trip="round-trip",
                seat=seat_type,
                passengers=Passengers(adults=adults),
            )

            if result and result.flights:
                if return_cheapest_only:
                    cheapest = min(result.flights, key=lambda f: parse_price(f.price))
                    results_data.append({
                        "departure_date": dep.strftime("%Y-%m-%d"),
                        "return_date": ret.strftime("%Y-%m-%d"),
                        "cheapest_flight": flight_to_dict(cheapest),
                    })
                else:
                    results_data.append({
                        "departure_date": dep.strftime("%Y-%m-%d"),
                        "return_date": ret.strftime("%Y-%m-%d"),
                        "flights": [flight_to_dict(f) for f in result.flights],
                    })
        except Exception as e:
            msg = f"Error for {dep} -> {ret}: {type(e).__name__}: {str(e)[:100]}"
            print(f"MCP Tool Error: {msg}", file=sys.stderr)
            if msg not in error_messages:
                error_messages.append(msg)

    print("MCP Tool: range search complete.", file=sys.stderr)

    results_key = "cheapest_option_per_date_pair" if return_cheapest_only else "all_round_trip_options"
    return json.dumps({
        "search_parameters": {
            "origin": origin, "destination": destination,
            "start_date": start_date_str, "end_date": end_date_str,
            "min_stay_days": min_stay_days, "max_stay_days": max_stay_days,
            "adults": adults, "seat_type": seat_type,
            "return_cheapest_only": return_cheapest_only,
        },
        results_key: results_data,
        "errors_encountered": error_messages or None,
    }, indent=2)


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8000))
    print(f"Starting Flights MCP server on {mcp.settings.host}:{mcp.settings.port}", file=sys.stderr)
    mcp.run(transport="streamable-http")
