import logging
from datetime import timedelta
from enum import Enum
from os.path import abspath, dirname, join
from typing import List, Optional

from pydantic import BaseModel

# Configure logging message format.
LOGGER_FORMAT = "%(name)s %(asctime)s %(levelname)s %(message)s"
LOGGER_LEVEL = logging.INFO
logging.basicConfig(format=LOGGER_FORMAT, level=LOGGER_LEVEL)

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


class TeamAbbrev(str, Enum):
    """Available team abbreviations."""

    ANA = "ANA"
    BOS = "BOS"
    BUF = "BUF"
    CAR = "CAR"
    CBJ = "CBJ"
    CGY = "CGY"
    CHI = "CHI"
    COL = "COL"
    DAL = "DAL"
    DET = "DET"
    EDM = "EDM"
    FLA = "FLA"
    LAK = "LAK"
    MIN = "MIN"
    MTL = "MTL"
    NJD = "NJD"
    NSH = "NSH"
    NYI = "NYI"
    NYR = "NYR"
    OTT = "OTT"
    PHI = "PHI"
    PIT = "PIT"
    SEA = "SEA"
    SJS = "SJS"
    STL = "STL"
    TBL = "TBL"
    TOR = "TOR"
    UTA = "UTA"
    VAN = "VAN"
    VGK = "VGK"
    WPG = "WPG"
    WSH = "WSH"


class Game(BaseModel):
    """Holds information for a single game."""

    home_team_abbrev: (
        str  # This should be a regular string so we can handle special games.
    )
    home_team_name: str
    away_team_abbrev: (
        str  # This should be a regular string so we can handle special games.
    )
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

    team: TeamAbbrev
    season: int
    games: List[Game]
    timestamp: str


class CalendarType(str, Enum):
    """Possible types of calendars served."""

    FULL = "full"
    HOME = "home"
    AWAY = "away"
