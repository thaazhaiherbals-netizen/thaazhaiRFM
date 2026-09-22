# Order processor worker

Run with python -m workers.order_processor, or start the worker service in compose.yaml.
See docs/PROCESSING_JOBS.md for the queue, restart behavior, Swagger flow and token setup.
The worker processes only explicit jobs; starting it alone does not process raw orders.
