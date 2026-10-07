import random


PERCENTAGES = [0.40, 0.25, 0.35]


def distribute_amounts(total_amount: int) -> list[int]:
    """Split total across 3 tasks using shuffled 40/25/35%; third gets remainder."""
    percents = PERCENTAGES.copy()
    random.shuffle(percents)

    first = round(total_amount * percents[0])
    second = round(total_amount * percents[1])
    third = total_amount - first - second

    amounts = [first, second, third]
    assert sum(amounts) == total_amount
    return amounts
