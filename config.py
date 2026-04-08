COST_OF_LIVING = 5
COST_PER_ACTION = 2
COST_SELLER_LISTING = 1
COST_MUTATION = 10
REWARD_WINNER = 100
PENALTY_LOSER = 20
REWARD_PER_USD_SOLD = 50
PENALTY_NO_SALE = 5
REPRODUCTION_THRESHOLD = 500
FARM_DEATH_THRESHOLD = 0
FARM_EXPANSION_ROI = 0.3
CAPITAL_BONUS_GOOD_FARM = 500
CAPITAL_PENALTY_BAD_FARM = 300
CYCLE_INTERVAL_SECONDS = 5
INITIAL_CREDITS = 200
NO_PROFIT_THRESHOLD = 5

DISCORD_ENABLED = True           # Activado — token configurado en variable de entorno
DISCORD_TARGET_CHANNELS = ["1488986417182019780"]

# Gumroad product URLs by niche (public permalinks)
GUMROAD_PRODUCT_URLS: dict[str, str] = {
    "data_cleaning": "https://leonix63.gumroad.com/l/fpwkdg",
    "auto_reports": "https://leonix63.gumroad.com/l/frhqhf",
    "product_listing": "https://leonix63.gumroad.com/l/jzzsv",
    "monetized_content": "https://leonix63.gumroad.com/l/wnuah",
}

# Gumroad internal product IDs (required for API PUT requests)
GUMROAD_PRODUCT_IDS: dict[str, str] = {
    "data_cleaning": "EIvVFKNtICACXEnRyKlE8A==",
    "auto_reports": "8yBjBIZjBkQF-YYR_yeS3A==",
    "product_listing": "YD_J2-XUskVt2Ts-vqnzug==",
    "monetized_content": "WW09wqbFXXQuXTsxqqV-hg==",
}

SHOPIFY_ENABLED = False          # Se activa cuando las credenciales OAuth estén configuradas
GUMROAD_ENABLED = True           # Activado — token configurado en variable de entorno
LEMONSQUEEZY_ENABLED = False     # DESHABILITADO PERMANENTEMENTE — no usar esta plataforma
GOOGLE_DRIVE_ENABLED = False     # DESHABILITADO — Google Drive no funciona con service accounts sin Workspace
BACKBLAZE_ENABLED = True         # Activado — credenciales B2_KEY_ID y B2_APPLICATION_KEY

# Farm activation flags
REACT_NEXTJS_FARM_ACTIVE = True
DEVOPS_CLOUD_FARM_ACTIVE = True
MOBILE_DEV_FARM_ACTIVE = True

# Google Drive folder IDs by farm type (DEPRECATED - use Backblaze)
GOOGLE_DRIVE_FOLDER_IDS: dict[str, str] = {
    "data_cleaning": "1qjVs8bQ6XzuSzuMin1fvR82wA-7NZza9",
    "auto_reports": "1tcd4KREz_ABMzORmg_a9s5BXvuZHsjxD",
    "product_listing": "1P7SCGJ0m8J-wLg678eZWkvYfcm5y5v7g",
    "monetized_content": "1GO03fu8aM0nXNYxNBOSFb4ESkWwgidcg",
    "react_nextjs": "19kIvsTU7O7ReSGrBOaAoBIkZ3OZmXXwL",
    "devops_cloud": "1A69s783nK31hGAqtjb8yoqoHKU-kG1Ic",
    "mobile_dev": "1o9Xx3yA2E6v_rcucaG14mIuXM_r-R9Ub",
}

# Backblaze B2 bucket names by farm type
BACKBLAZE_BUCKETS: dict[str, str] = {
    "data_cleaning": "multifarm-data-cleaning",
    "auto_reports": "multifarm-auto-reports",
    "product_listing": "multifarm-product-listing",
    "monetized_content": "multifarm-monetized-content",
    "react_nextjs": "multifarm-react-nextjs",
    "devops_cloud": "multifarm-devops-cloud",
    "mobile_dev": "multifarm-mobile-dev",
}
