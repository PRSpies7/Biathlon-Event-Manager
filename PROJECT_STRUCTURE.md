# Biathlon Event Manager v1.7 Project Structure

```text
biathlon_event_manager_v1.7/
├── app.py
├── requirements.txt
├── README.md
├── PROJECT_STRUCTURE.md
├── run_app.bat
├── run_app.sh
│
├── data/
│   ├── biathlon_events.sqlite
│   ├── Master Entries Excel.xlsx
│   ├── TimeDrops JSON example.json
│   ├── Run Results LG4.xlsx
│   ├── Swim TXT file.txt
│   ├── Master LG4.xlsx
│   └── Master LG4.xml
│
├── database/
│   ├── db.py
│   └── repository.py
│
├── parsers/
│   ├── master_entries.py
│   ├── run_results_excel.py
│   └── swim_results.py
│
├── exporters/
│   ├── master_excel.py
│   ├── results_xml.py
│   ├── timedrops_json.py
│   └── swim_timekeeper.py
│
├── services/
│   └── results_service.py
│
├── validation/
│   └── validators.py
│
├── ui/
│   ├── helpers.py
│   ├── phase1_setup.py
│   ├── phase2_positions.py
│   ├── phase3_processing.py
│   └── phase4_export.py
│
└── tests/
    ├── test_parsers.py
    └── test_v11.py
```

SQLite is the persistent Master Dataset. The application does not use Streamlit session state as the authoritative store for event data.
