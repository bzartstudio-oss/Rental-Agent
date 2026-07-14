# 12 — Glossary

Terms used across these docs, defined once here so each individual doc doesn't have to re-explain them.

| Term | Meaning |
|---|---|
| **Search Request** | The user's input describing what rentals to find. See [04_Search_Request.md](04_Search_Request.md). |
| **Platform** | A single rental site/source the agent can query. See [03_Data_Model.md](03_Data_Model.md). |
| **Connector** | The code that knows how to query one specific `Platform` and return raw results. See [06_Connector_Framework.md](06_Connector_Framework.md). |
| **Raw Listing** | A single result exactly as a connector returned it, before normalization. |
| **Listing** | A normalized rental result, in the shared schema every downstream component understands. See [03_Data_Model.md](03_Data_Model.md). |
| **Analysis Engine** | The component that turns Raw Listings into normalized Listings. See [07_Analysis_Engine.md](07_Analysis_Engine.md). |
| **Ranked Listing** | A Listing plus a score/rank relative to a specific Search Request. See [08_Ranking_System.md](08_Ranking_System.md). |
| **Report** | The final output artifact a person reads — built from Ranked Listings. See [09_Report_System.md](09_Report_System.md). |
| **Platform Discovery** | The step that decides which Platforms are relevant to a given Search Request. See [05_Platform_Discovery.md](05_Platform_Discovery.md). |

Add new terms here as they're introduced elsewhere in the docs — don't let a term get used in two docs with two different meanings.
