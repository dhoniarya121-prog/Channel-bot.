from utils.buttons import parse_post_link

MAX_SPAN = 200_000


def parse_range(text: str):
    """'https://t.me/c/123/900' -> (1, 900) | '500' -> (1, 500) | '100 900' -> (100, 900) | None if invalid."""
    text = (text or "").strip()
    ref = parse_post_link(text)
    if ref:
        return 1, ref[1]
    parts = text.replace("-", " ").split()
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 1:
        nums = [1, nums[0]]
    if len(nums) != 2 or nums[0] < 1 or nums[1] < nums[0] or nums[1] - nums[0] > MAX_SPAN:
        return None
    return nums[0], nums[1]
