# Invoice templates (for frontend)

Send this file with `API.md`. Backend runs on the API PC; frontend only picks a template **id** (`1`–`14`).

**API base (example):** `http://10.100.4.15:8000`

---

## Template list (dropdown)

| id | Label (show in UI) | Company / style |
|----|--------------------|-----------------|
| 1 | MAXIS | Invoice1-MAXIS |
| 2 | Forest Tech | Invoice02-ForestTechInc1 |
| 3 | Radnor Innovations | Invoice03-RadnorInnovationsInc |
| 4 | App Founders | Invoice04-APPFOUNDERSINC |
| 5 | Dynamo Creatives | Invoice05-DynamoCreativesInc |
| 6 | Ravotek | Invoice06-RavotekInc |
| 7 | Ignitai | Invoice07-IgnitaiInc |
| 8 | Coretechify | Invoice08-CoretechifyInc |
| 9 | Ecomify | Invoice09-EcomifyInc |
| 10 | Cozy Home Essentials | Invoice10-CozyHomeEssentials |
| 11 | Beecodify | Invoice11-BeecodifyInc |
| 12 | Bravix Technologies | Invoice12-BravixTechnologiesInc |
| 13 | Alpha Digital | Invoice13-AlphaDigitalInc |
| 14 | Synergo | Invoice14-SynergoInc |

Use **`id`** as `invoice_template` in generate requests.

---

## Load from API (preferred)

```http
GET {BASE_URL}/api/templates/status
Cookie: invoice_session=...
```

Frontend tip: build select options from `Object.values(templates)` → `{ value: id, label }`.
