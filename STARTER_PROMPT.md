Read CLAUDE.md in this folder and follow it exactly. We will run the BI flow one step at a time.

1. Confirm .env exists and has every variable from .env.example filled (do not print the values). If something is missing, tell me which variable and stop.
2. Make sure Metabase is running (Docker) and set up (`python metabase_setup.py`), then run `python flow.py status` and tell me where we are.
3. Run the next step only. Show me the result and STOP for my approval. I will say "approve" before you run `python flow.py approve <step>`.
4. Repeat until all nine steps are approved. If I give you several tables, profile them all and use the model step to propose the joins. If I ask to start over, use `python flow.py reset`.

My Snowflake view or table is: <NAME HERE>
My BI tool is: Metabase

Do not use a browser. Do not create files beyond what CLAUDE.md requires.
