from dataclasses import dataclass, field


@dataclass(frozen=True)
class LineItemConfig:
    table_index: int = 0
    line_item_rows: list[int] = field(default_factory=lambda: [1, 2, 3])
    desc_col: int = 0
    amount_col: int = 1
    # When True, resolve tables via body XML (includes textbox tables).
    use_all_tables: bool = False
    # Extra item rows to blank after filling the 3 club lines.
    clear_rows: tuple[int, ...] = ()


# Locked line-item layout per Word template in Data/word/ (Invoices 1–14).
LINE_ITEM_CONFIGS: dict[int, LineItemConfig] = {
    1: LineItemConfig(table_index=1, line_item_rows=[1, 2, 3], desc_col=0, amount_col=1),
    2: LineItemConfig(table_index=1, line_item_rows=[5, 6, 7], desc_col=0, amount_col=2),
    3: LineItemConfig(table_index=1, line_item_rows=[1, 2, 3], desc_col=0, amount_col=1),
    4: LineItemConfig(table_index=2, line_item_rows=[1, 2, 3], desc_col=1, amount_col=3),
    5: LineItemConfig(table_index=1, line_item_rows=[1, 2, 3], desc_col=0, amount_col=2),
    # New company templates
    6: LineItemConfig(
        table_index=0,
        line_item_rows=[1, 2, 3],
        desc_col=1,
        amount_col=4,
        clear_rows=(4, 5, 6),
    ),
    7: LineItemConfig(
        table_index=0,
        line_item_rows=[2, 3, 4],
        desc_col=0,
        amount_col=3,
        use_all_tables=True,
        clear_rows=(5,),
    ),
    8: LineItemConfig(
        table_index=0,
        line_item_rows=[1, 2, 3],
        desc_col=0,
        amount_col=3,
        clear_rows=(4, 5),
    ),
    9: LineItemConfig(
        table_index=1,
        line_item_rows=[0, 1, 2],
        desc_col=1,
        amount_col=4,
        clear_rows=(3, 4, 5, 6),
    ),
    10: LineItemConfig(
        table_index=0,
        line_item_rows=[1, 2, 3],
        desc_col=0,
        amount_col=3,
        clear_rows=(4, 5, 6),
    ),
    11: LineItemConfig(
        table_index=0,
        line_item_rows=[1, 2, 3],
        desc_col=0,
        amount_col=3,
        clear_rows=(4, 5),
    ),
    12: LineItemConfig(
        table_index=0,
        line_item_rows=[1, 2, 3],
        desc_col=0,
        amount_col=4,
        clear_rows=(4, 5),
    ),
    13: LineItemConfig(
        table_index=1,
        line_item_rows=[1, 2, 3],
        desc_col=0,
        amount_col=3,
    ),
    14: LineItemConfig(
        table_index=0,
        line_item_rows=[1, 4, 6],
        desc_col=0,
        amount_col=0,
    ),
}


def line_item_config(invoice_number: int) -> LineItemConfig:
    if invoice_number not in LINE_ITEM_CONFIGS:
        raise ValueError(f"No line-item config for invoice {invoice_number}")
    return LINE_ITEM_CONFIGS[invoice_number]
