"""Configuration for the Gulf & Middle East Strikes Dashboard."""

# Twitter/X accounts to monitor, organized by country
ACCOUNTS = [
    {
        "country": "Bahrain",
        "username": "BDF_Bahrain",
        "flag": "\ud83c\udde7\ud83c\udded",
        "color": "#CE1126",
        "description": "Bahrain Defence Force",
        "parse_mode": "count_posts",  # No numbers in text; each post = 1 interception event
    },
    {
        "country": "Saudi Arabia",
        "username": "modgovksa",
        "flag": "\ud83c\uddf8\ud83c\udde6",
        "color": "#006C35",
        "description": "Ministry of Defense - KSA",
        "parse_mode": "arabic_per_incident",  # "اعتراض وتدمير N مسيّرات"
    },
    {
        "country": "Kuwait",
        "username": "KuwaitArmyGHQ",
        "flag": "\ud83c\uddf0\ud83c\uddfc",
        "color": "#007A3D",
        "description": "Kuwait Army General Staff HQ",
        "parse_mode": "arabic_per_incident",
    },
    {
        "country": "UAE",
        "username": "modgovae",
        "flag": "\ud83c\udde6\ud83c\uddea",
        "color": "#00732F",
        "description": "Ministry of Defence - UAE",
        "parse_mode": "uae_bilingual",  # Bilingual with daily + cumulative totals
    },
    {
        "country": "Israel",
        "username": "TheStudyofWar",
        "flag": "\ud83c\uddee\ud83c\uddf1",
        "color": "#0038B8",
        "description": "The Study of War — Israel Coverage",
        "parse_mode": "keyword_filter",
        "filter_keywords": ["Israel", "IDF", "Israeli", "Gaza", "West Bank", "Hezbollah",
                            "Lebanon", "Hamas", "Tel Aviv", "Jerusalem", "Netanyahu"],
    },
    {
        "country": "Iran",
        "username": "TheStudyofWar",
        "flag": "\ud83c\uddee\ud83c\uddf7",
        "color": "#C41E3A",
        "description": "The Study of War — Iran Coverage",
        "parse_mode": "keyword_filter",
        "filter_keywords": ["Iran", "Iranian", "IRGC", "Tehran", "Khamenei", "Isfahan",
                            "Bushehr", "Natanz", "Persian Gulf", "Strait of Hormuz"],
    },
]

# How many tweets to fetch per account
TWEETS_PER_ACCOUNT = 10

# Max historical tweets to fetch per account
MAX_HISTORICAL_TWEETS = 300

# Cache refresh interval in seconds (1 hour)
REFRESH_INTERVAL = 3600

# Flask server settings
HOST = "0.0.0.0"
PORT = 5000
DEBUG = True
