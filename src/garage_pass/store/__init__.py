"""The Postgres store: a port, a migration and a chokepoint.

The engine (``garage_pass.access``) never imports this package. Everything in
here imports ``psycopg`` lazily, inside the function that needs it, so that
importing ``garage_pass`` on a machine with no driver is not an error and the
access answer can be embedded in a lane with nothing but the standard library.
"""
