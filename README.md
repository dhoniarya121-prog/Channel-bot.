# ROAROIC CAPTION BOT v3 (button panel)

Channel mein jo bhi video/file post hoti hai, bot uska caption ROAROIC design mein edit karta hai aur chahe to
post ke neeche **link buttons** bhi laga deta hai. Ab sab kuch bot ke **buttons/menu** se hota hai — file edit karne ki zaroorat nahi.

## Setup
1. `pip install -r requirements.txt`
2. `.env.example` ko `.env` banao aur API_ID, API_HASH, BOT_TOKEN, OWNER_ID bharo.
3. Bot ko channel mein **admin** banao (**Edit messages** right).
4. `python bot.py`, phir bot ko private mein `/start` ya `/menu` bhejo.

## Menu kya karta hai
`/menu` -> **My Channels** -> channel chuno. Har channel ki **apni alag settings**:

| Button | Kaam |
|---|---|
| 📝 Caption ON/OFF | is channel ke naye posts par auto caption |
| 🔘 Buttons ON/OFF | is channel ke naye posts par auto link buttons |
| 🎨 Template | ROAROIC Full / Simple / Quote / Classic / Minimal, ya ✍️ apna custom design |
| 🔗 Links | links ke naam + URL add / change / delete (design mein use hote hain) |
| 🔘 Manage buttons | **➕ Add button** (2 step: text, link), 📋 Add many, edit, up/down, delete, 1 ya 2 per row |
| 🧹 Old links | purane promo links jo caption se hatane hain |
| ▶️ Run on old posts | sirf is channel par: Captions / Buttons / Both / Remove buttons — range chuno (`900`, `100 900` ya post link) |
| 👁 Preview | design + buttons ka sample |

* **➕ Add Channel**: channel ka koi post forward karo, ya ID / @username / link bhejo. Bot khud bhi naya channel pehchan leta hai (pehle post par) aur aapko batata hai.
* **🌐 Default Settings**: jis channel ki apni setting nahi, wo isse chalta hai.
* Link bhejte waqt `@name` likhna kaafi hai (`@roaroic1` = `https://t.me/roaroic1`).

## Commands (owner)
`/menu` `/preview` `/id` `/cancel` `/backup` `/restore` (backup file par reply) `/oldposts …` `/stopold`

## Settings kahan save hoti hain
Ek chhoti JSON file (`DATA_FILE`). Render par `render.yaml` mein persistent disk laga hai (`/var/data/settings.json`),
isliye redeploy par settings bani rehti hain. Safety ke liye **💾 Backup** (ya `/backup`) se file le lo; `/restore` se wapas.

## Tests
`python -m unittest discover -s tests -t .`
