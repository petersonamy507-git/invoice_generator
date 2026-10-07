from dataclasses import dataclass, field
from datetime import date


@dataclass
class InvoiceTask:
    main_task: str
    sub_task: str
    amount: int


@dataclass
class InvoiceData:
    person_name: str
    company_name: str
    email: str
    invoice_date: date
    structure_number: int
    total_amount: int
    tasks: list[InvoiceTask]


@dataclass
class WordInvoiceData:
    person_name: str
    company_name: str
    email: str
    total_amount: int
    invoice_number: int
    tasks: list[InvoiceTask] = field(default_factory=list)
    bank: str = ""
    iban: str = ""
    branch_code: str = ""
    sheet_invoice_no: str = ""
    document_invoice_no: str = ""
