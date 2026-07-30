@echo off
rem Inno Setup SignTool wrapper for Azure Trusted Signing.
rem Inno passes the file to sign as %1. SIGNTOOL, TS_DLIB and TS_METADATA are
rem exported by the workflow before iscc runs; Azure auth comes from the
rem AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET env (DefaultAzureCredential).
"%SIGNTOOL%" sign /fd SHA256 /tr http://timestamp.acs.microsoft.com/ /td SHA256 /dlib "%TS_DLIB%" /dmdf "%TS_METADATA%" "%~1"
