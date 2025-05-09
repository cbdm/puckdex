import json
import logging
from datetime import datetime, timezone
from os import getenv
from os.path import abspath, dirname, join
from typing import Dict, List
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from icalendar import Calendar, Event

from cache import cache_this
from utils import (
    ABBREV_TO_NAME_MAP,
    SCHEDULE_API_URL,
    CalendarType,
    Game,
    Schedule,
    TeamAbbrev,
)

app = FastAPI()

# Use the absolute path for the templates and static folder so the webserver can find it.
templates = Jinja2Templates(directory=join(dirname(abspath(__file__)), "templates"))
app.mount(
    "/static",
    StaticFiles(directory=join(dirname(abspath(__file__)), "static")),
    name="static",
)
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


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """Page with more information about the project and how to use it."""
    return templates.TemplateResponse(request=request, name="about.html.j2")


# Cache reponses from the NHL API so we don't have to fetch a schedule for each request.
@cache_this
async def _fetch_schedule(team: TeamAbbrev) -> Dict:
    """Fetch the team schedule from the NHL API and parse the JSON response into a dict."""
    logger.warning("Requesting schedule for %s from NHL API.", team.name)
    response = requests.get(SCHEDULE_API_URL.format(team_abbrev=team.name), timeout=120)
    if not response.status_code == 200:
        raise HTTPException(
            status_code=404,
            detail=f"Request to NHL API returned with a status of {response.status_code}",
        )
    return json.loads(response.text)


async def _parse_schedule(team: TeamAbbrev, data: Dict) -> Schedule:
    """Parse the schedule information from the NHL API JSON response."""
    logger.warning("Parsing NHL response to create schedule for %s", team.name)

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
                home_score=game["homeTeam"]["score"] if is_over else 0,
                away_score=game["awayTeam"]["score"] if is_over else 0,
                venue=game.get("venue", {}).get("default", ""),
                where_to_watch=list(
                    {
                        f"[{b['countryCode']}] {b['network']}"
                        for b in game.get("tvBroadcasts", [])
                    }
                ),
            )
        )

    return Schedule(
        team=team,
        season=data["currentSeason"],
        games=games,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def _create_fresh_schedule(team: TeamAbbrev) -> Schedule:
    """Create and return a Schedule with current data for the team."""
    api_json_response = await _fetch_schedule(team)
    return await _parse_schedule(team, api_json_response)  # type: ignore[arg-type]


async def _filter_schedule(s: Schedule, cal_type: CalendarType) -> Schedule:
    """Filter the given schedule to have only the games that match the calendar type."""
    if cal_type == CalendarType.FULL:
        # For complete schedule, no filtering needed.
        return s

    elif cal_type == CalendarType.HOME:
        # Ignore non-home games for home-only calendars.
        return Schedule(
            team=s.team,
            season=s.season,
            timestamp=s.timestamp,
            # Ignore non-home games for home-only calendars.
            games=[g for g in s.games if g.home_team_abbrev == s.team],
        )

    elif cal_type == CalendarType.AWAY:
        # Ignore non-away games for away-only calendars.
        return Schedule(
            team=s.team,
            season=s.season,
            timestamp=s.timestamp,
            games=[g for g in s.games if g.away_team_abbrev == s.team],
        )

    else:
        # Should not reach here: pydantic should stop any routes with an invalid value for cal_type.
        raise HTTPException(404, f"Unknown calendar type: {cal_type}")


async def create_fresh_calendar(team: TeamAbbrev, cal_type: CalendarType) -> Response:
    """Create and return an ics calendar with the given team's schedule."""
    logger.warning("Creating fresh %s calendar for %s", cal_type.name, team.name)

    # Create empty calendar with required properties.
    cal = Calendar()
    cal.add("prodid", "-//Puckdex//puckdex.cbdm.app//EN")
    cal.add("version", "2.0")
    cal.add("METHOD", "PUBLISH")
    calname = f"{ABBREV_TO_NAME_MAP.get(team.name, team.name)} - {cal_type.name} Calendar".title()
    cal.add("X-WR-CALNAME", calname)
    cal.add("X-WR-TIMEZONE", "UTC")

    # Get schedule data.
    schedule = await _create_fresh_schedule(team)
    filtered_schedule = await _filter_schedule(schedule, cal_type)

    # Add one calendar event for each scheduled game.
    dtstamp = datetime.now(tz=ZoneInfo("UTC"))
    for game in filtered_schedule.games:
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
        start_dt = datetime.fromisoformat(game.start_utc_timestamp)
        event.add("summary", game_info)
        event.add("dtstamp", dtstamp)
        event.add("dtstart", start_dt)
        event.add("dtend", start_dt + game.length)
        if game.venue:
            event.add("location", game.venue)
        if extra_info:
            event.add("description", extra_info.strip())

        local_uid = f"{start_dt.date()}_{game.home_team_abbrev}_{game.away_team_abbrev}"
        event.add("uid", f"{local_uid}@puckdex.cbdm.app")

        # Add event to calendar.
        cal.add_component(event)

    # Return the calendar in ics format.
    return Response(content=cal.to_ical().decode("utf-8"), media_type="text/calendar")


@app.get("/{calendar_type}/{team}.ics", response_class=FileResponse)
async def get_calendar(calendar_type: CalendarType, team: TeamAbbrev) -> Response:
    """Return an .ics calendar of the specified type and team in the current NHL season."""
    logger.warning("Received request of %s for %s", calendar_type, team)
    return await create_fresh_calendar(team, calendar_type)


@app.get("/next/{calendar_type}/{team}")
async def get_next_game(calendar_type: CalendarType, team: TeamAbbrev) -> Game:
    """Return information for the next game in the team's full/home/away calendar."""
    logger.warning("Received request for the next %s game for %s", calendar_type, team)

    # Get a current schedule for the team.
    schedule = await _create_fresh_schedule(team)
    filtered_schedule = await _filter_schedule(schedule, calendar_type)

    # Parse through schedule and find the first game on a future date.
    # IMPORTANT: This assumes the schedule is sorted!
    #            As of 2025-03-16, the NHL API response is already sorted.
    now = datetime.now(timezone.utc)
    for game in filtered_schedule.games:
        if (datetime.fromisoformat(game.start_utc_timestamp) + game.length) > now:
            # Return the first game that ends on a future date.
            return game

    # There are no games on a future date, we don't know when is the next one.
    # Return a dummy Game object with TBD for opposing team.
    return Game(
        home_team_abbrev=team.name,
        home_team_name=ABBREV_TO_NAME_MAP[team.name],
        away_team_abbrev="TBD",
        away_team_name="To Be Determined",
        start_utc_timestamp="2100-01-01T00:00:00Z",
    )


@app.get("/last/{calendar_type}/{team}")
async def get_last_game(calendar_type: CalendarType, team: TeamAbbrev) -> Game:
    """Return information for the most recent game in the team's full/home/away calendar."""
    logger.warning("Received request for the last %s game for %s", calendar_type, team)

    # Get a current schedule for the team.
    schedule = await _create_fresh_schedule(team)
    filtered_schedule = await _filter_schedule(schedule, calendar_type)

    # Create a dummy game in case we don't find a past game in the schedule.
    last_game = Game(
        home_team_abbrev=team.name,
        home_team_name=ABBREV_TO_NAME_MAP[team.name],
        away_team_abbrev="???",
        away_team_name="Unknown",
        start_utc_timestamp="1970-01-01T00:00:00Z",
    )

    # Parse through schedule and find the past game that ended the closest to current date.
    # IMPORTANT: This assumes the schedule is sorted!
    #            As of 2025-03-16, the NHL API response is already sorted.
    now = datetime.now(timezone.utc)
    i = 0
    while i < len(filtered_schedule.games) and now > (
        datetime.fromisoformat(filtered_schedule.games[i].start_utc_timestamp)
        + filtered_schedule.games[i].length
    ):
        last_game = filtered_schedule.games[i]
        i += 1

    return last_game
