# ROAROIC CAPTION BOT (no database)

Channel mein jo bhi video/file post hoti hai, bot uska caption ROAROIC design mein edit kar deta hai:
`[ @roaroic0 ]` prefix + saare links + divider + `ROAROIC MOVIE'S || 0.1`.

## Setup
1. `pip install -r requirements.txt`
2. `.env.example` ko `.env` banao aur API_ID, API_HASH, BOT_TOKEN, OWNER_ID bharo (SOURCE_CHANNELS optional).
3. Bot ko channel mein **admin** banao (Edit messages right).
4. `python bot.py`

## Commands (owner)
* `/preview` - caption design dekho
* `/oldposts https://t.me/c/1234567890/900` - pehle se padi posts (1 se 900 tak) edit
* `/oldposts -1001234567890 100 900` - 100 se 900 tak
* `/stopold` - job rok do
* `/id` - kisi chat ka ID

## Links / design badalna
`settings.py` (LINKS, TEMPLATE, OLD_LINKS) aur `utils/captions.py` (ROAROIC_LINKS, ROAROIC_TEMPLATE) edit karo, phir redeploy.
Purane promo links hatane ke liye unhe `OLD_LINKS` mein daalo.

## Tests
`python -m unittest discover -s tests -t .`
