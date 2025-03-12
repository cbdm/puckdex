import json
import logging
from datetime import datetime, timezone
from os import getenv
from os.path import abspath, dirname, join
from typing import Dict, List

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from ics import Calendar, Event

from dict_cache import cache_this
from utils import ABBREV_TO_NAME_MAP, SCHEDULE_API_URL, CalendarType, Game, Schedule

app = FastAPI()

# Use the absolute path for the templates folder so the webserver can find it.
templates = Jinja2Templates(directory=join(dirname(abspath(__file__)), "templates"))
# Create a logger to help debug future issues.
logger = logging.getLogger(getenv("LOGGER_NAME", __name__))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page to show available calendars."""
    return templates.TemplateResponse(
        request=request,
        name="index.html.j2",
        context={"abbrev_map": ABBREV_TO_NAME_MAP},
    )


# Cache reponses from the NHL API so we don't have to fetch a schedule for each request.
@cache_this
async def _fetch_schedule(team_abbrev: str) -> Dict:
    """Fetch the team schedule from the NHL API and parse the JSON response into a dict."""
    logger.warning("Requesting schedule for '%s' from NHL API.", team_abbrev)
    response = requests.get(
        SCHEDULE_API_URL.format(team_abbrev=team_abbrev), timeout=120
    )
    if not response.status_code == 200:
        raise HTTPException(
            status_code=404,
            detail=f"Request to NHL API returned with a status of {response.status_code}",
        )
    return json.loads(response.text)


async def _parse_schedule(team_abbrev: str, data: Dict) -> Schedule:
    """Parse the schedule information from the NHL API JSON response."""
    logger.warning("Parsing NHL response to create schedule for '%s'", team_abbrev)

    games: List[Game] = []
    for game in data["games"]:

        # Find information of unknown team names.
        # This is helpful for special games, e.g., in 2024 Buffalo played EHC Red Bull München
        home_team_abbrev = game["homeTeam"]["abbrev"]
        home_team_name = ABBREV_TO_NAME_MAP.get(home_team_abbrev, "")
        if not home_team_name:
            home_team_name = game["homeTeam"]["commonName"]["default"]

        away_team_abbrev = game["awayTeam"]["abbrev"]
        away_team_name = ABBREV_TO_NAME_MAP.get(away_team_abbrev, "")
        if not away_team_name:
            away_team_name = game["awayTeam"]["commonName"]["default"]

        # Check if the game is over.
        is_over = game["gameState"] in {"FINAL", "OFF"}

        # Create a new game instance.
        games.append(
            Game(
                home_team_abbrev=home_team_abbrev,
                home_team_name=home_team_name,
                away_team_abbrev=away_team_abbrev,
                away_team_name=away_team_name,
                start_utc_timestamp=game["startTimeUTC"],
                ended=is_over,
                home_score=game["homeTeam"]["score"] if is_over else None,
                away_score=game["awayTeam"]["score"] if is_over else None,
                venue=game.get("venue", {}).get("default"),
                where_to_watch=[
                    f"[{b['countryCode']}] {b['network']}"
                    for b in game.get("tvBroadcasts", [])
                ],
            )
        )

    return Schedule(
        team_abbrev=team_abbrev,
        season=data["currentSeason"],
        games=games,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def create_fresh_calendar(team_abbrev: str, cal_type: CalendarType) -> Response:
    """Create and return an ics calendar with the given team's schedule."""
    logger.warning("Creating fresh %s calendar for '%s'", cal_type.name, team_abbrev)
    if team_abbrev not in ABBREV_TO_NAME_MAP:
        raise HTTPException(status_code=404, detail=f"Team '{team_abbrev}' not found")

    # Create empty calendar.
    cal = Calendar()

    # Get schedule data.
    api_json_response = await _fetch_schedule(team_abbrev)
    schedule = await _parse_schedule(team_abbrev, api_json_response)  # type: ignore[arg-type]

    # Add one calendar event for each scheduled game.
    for game in schedule.games:
        if cal_type == CalendarType.HOME and game.home_team_abbrev != team_abbrev:
            # Ignore non-home games for home-only calendars.
            continue
        if cal_type == CalendarType.AWAY and game.away_team_abbrev != team_abbrev:
            # Ignore non-away games for away-only calendars.
            continue

        # Format game information.
        home_team = game.home_team_name
        home_score = f"({game.home_score}) " if game.ended else ""
        away_team = game.away_team_name
        away_score = f" ({game.away_score})" if game.ended else ""
        game_info = f"{away_team}{away_score} @ {home_score}{home_team}"

        # Format extra information
        extra_info = ""
        if game.where_to_watch:
            extra_info += f"Where to watch: {', '.join(game.where_to_watch)}\n"

        # Create calendar event.
        event = Event()
        event.name = game_info
        event.begin = game.start_utc_timestamp
        event.duration = game.length
        if game.venue:
            event.location = game.venue
        if extra_info:
            event.description = extra_info.strip()

        # Add event to calendar.
        cal.events.add(event)

    # Return the calendar in ics format.
    return Response(content=cal.serialize(), media_type="text/calendar")


@app.get("/full/{team_abbrev}.ics", response_class=FileResponse)
async def get_full_calendar(team_abbrev: str) -> Response:
    """Return an .ics calendar with all games of the given team in the current NHL season."""
    logger.warning("Received request for full calendar for '%s'", team_abbrev)
    return await create_fresh_calendar(team_abbrev, CalendarType.FULL)


@app.get("/home/{team_abbrev}.ics", response_class=FileResponse)
async def get_home_calendar(team_abbrev: str) -> Response:
    """Return an .ics calendar with the home games of the given team in the current NHL season."""
    logger.warning("Received request for home calendar for '%s'", team_abbrev)
    return await create_fresh_calendar(team_abbrev, CalendarType.HOME)


@app.get("/away/{team_abbrev}.ics", response_class=FileResponse)
async def get_away_calendar(team_abbrev: str) -> Response:
    """Return an .ics calendar with the away games of the given team in the current NHL season."""
    logger.warning("Received request for away calendar for '%s'", team_abbrev)
    return await create_fresh_calendar(team_abbrev, CalendarType.AWAY)
