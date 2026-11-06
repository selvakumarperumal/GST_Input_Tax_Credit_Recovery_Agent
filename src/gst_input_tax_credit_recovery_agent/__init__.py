def main():
    import uvicorn

    uvicorn.run("gst_input_tax_credit_recovery_agent.api:app", host="0.0.0.0", port=8000)
