# ROAROIC CAPTION BOT v3.1 (button panel, har user ke liye)

Channel mein jo bhi video/file post hoti hai, bot uska caption ROAROIC design mein edit karta hai aur chahe to
post ke neeche **link buttons** bhi laga deta hai. Ab sab kuch bot ke **buttons/menu** se hota hai — file edit karne ki zaroorat nahi.

## Har user use kar sakta hai
`PUBLIC_MODE=true` (default) mein koi bhi Telegram user bot ko `/start` karke **apne channels** manage kar sakta hai:
1. User apne channel mein bot ko **admin** banata hai (**Edit messages** right).
2. Bot mein **➕ Add Channel** → channel ka post forward kare (ya @username / link). Bot check karta hai ki user us channel ka **admin** hai.
3. Phir us channel ki caption, template, links, buttons, old posts — sab apni marzi se. Ek user ka data dusre ko nahi dikhta.
4. **🌐 My Default Settings**: user ke apne sab channels ki common setting (har user ki alag).

* Ek user ke channels ki limit: `MAX_CHANNELS_PER_USER` (default 10). `OWNER_ID` wale admin unlimited hain aur sab channels dekh/badal sakte hain.
* Jis channel ko kisi ne add nahi kiya, bot uske posts ko **chhuta nahi** (admin ko ek baar batata hai).
* Sirf apne liye chahiye? `PUBLIC_MODE=false`.
* Admin commands: `/stats`, `/ban <id>`, `/unban <id>`, `/backup`, `/restore`. Buttons ka auto-colour (blue/green/red cycle) kaam karta hai agar kurigram `style` support kare (bot start par log batata hai).

> Telegram mein CSS nahi chalti. Look badalne ke asli tareeke yehi hain: text styles (bold/italic/mono ...), unicode fonts, emojis, button ka rang aur layout.

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
| 🎨 Template | 5 purane + **20 naye designs** (Classic Clean, Quote Box, Cinematic, Premium Frame, Info Card, Neon Box ...) alag text styles mein (bold, italic, underline, mono, small caps, serif, script), ya ✍️ apna custom design. Pages (➡) se sab dikhte hain; 👁 Preview se pehle dekh lo |
| 🔗 Links | links ke naam + URL add / change / delete (design mein use hote hain) |
| 🔘 Manage buttons | **➕ Add button** (2 step: text, link), 📋 Add many, edit, up/down, delete. **Look:** layout 1/2/3 per row ya ✨ Smart (pehla bada, baaki jode mein), rang (🌈 Auto / 🔵 / 🟢 / 🔴 / ⚪), text font (Aa / 𝗔𝗮 / ꜱᴍ / 𝙼𝚘) |
| 🧹 Old links | purane promo links jo caption se hatane hain |
| ▶️ Run on old posts | sirf is channel par: Captions / Buttons / Both / Remove buttons — range chuno (`900`, `100 900` ya post link) |
| 👁 Preview | design + buttons ka sample |

* **➕ Add Channel**: channel ka koi post forward karo, ya ID / @username / link bhejo. Bot khud bhi naya channel pehchan leta hai (pehle post par) aur aapko batata hai.
* **🌐 Default Settings**: jis channel ki apni setting nahi, wo isse chalta hai.
* Link bhejte waqt `@name` likhna kaafi hai (`@roaroic1` = `https://t.me/roaroic1`).

## Commands
`/menu` `/channels` (aapke channels ka naam + link + ID) `/preview` `/id` `/cancel` `/oldposts …` `/stopold` — admin: `/stats` `/ban` `/unban` `/backup` `/restore` (backup file par reply)

## Settings kahan save hoti hain
Ek chhoti JSON file (`DATA_FILE`). Render par `render.yaml` mein persistent disk laga hai (`/var/data/settings.json`),
isliye redeploy par settings bani rehti hain. Safety ke liye **💾 Backup** (ya `/backup`) se file le lo; `/restore` se wapas.

## Tests
`python -m unittest discover -s tests -t .`
