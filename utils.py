from datetime import timedelta
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

# URL for the NHL API that provides team's schedules;
# ref: https://github.com/Zmalski/NHL-API-Reference
SCHEDULE_API_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team_abbrev}/now"

# How often the schedule should be updated.
UPDATE_FREQ = timedelta(days=2)

# Map team abbreviations to their full names.
ABBREV_TO_NAME_MAP = {
    "ANA": "Anaheim Ducks",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CAR": "Carolina Hurricanes",
    "CBJ": "Columbus Blue Jackets",
    "CGY": "Calgary Flames",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild",
    "MTL": "Montréal Canadiens",
    "NJD": "New Jersey Devils",
    "NSH": "Nashville Predators",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SEA": "Seattle Kraken",
    "SJS": "San Jose Sharks",
    "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Utah Hockey Club",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WPG": "Winnipeg Jets",
    "WSH": "Washington Capitals",
}


class Game(BaseModel):
    """Holds information for a single game."""

    home_team_abbrev: str
    home_team_name: str
    away_team_abbrev: str
    away_team_name: str
    start_utc_timestamp: str
    length: timedelta = timedelta(hours=3)
    ended: bool = False
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    venue: Optional[str] = None
    where_to_watch: Optional[List[str]] = None


class Schedule(BaseModel):
    """Holds information for all games in a season for a team."""

    team_abbrev: str
    season: int
    games: List[Game]
    timestamp: str


class CalendarType(Enum):
    """Possible types of calendars served."""

    FULL = 1
    HOME = 2
    AWAY = 3
