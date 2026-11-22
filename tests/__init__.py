import os

os.environ.setdefault("DATA_FILE", ":memory:")      # tests never touch a real settings file
os.environ.setdefault("OWNER_ID", "1")              # user 1 is the bot admin in tests; other ids are normal users
