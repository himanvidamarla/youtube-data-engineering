
@echo off
cd /d "%~dp0"

echo =====================================
echo STARTING YOUTUBE DATA PIPELINE
echo =====================================

call .venv\Scripts\activate.bat

echo.
echo STEP 1: INGESTING YOUTUBE DATA
python ingestion\youtube_client.py
if errorlevel 1 goto failure

echo.
echo STEP 2: LOADING POSTGRESQL WAREHOUSE
python ingestion\load_warehouse.py
if errorlevel 1 goto failure

echo.
echo STEP 3: RUNNING DATA QUALITY CHECKS
python validation\data_quality.py
if errorlevel 1 goto failure

echo.
echo STEP 4: RUNNING AUTOMATED TESTS
python -m pytest tests/ -v
if errorlevel 1 goto failure

echo.
echo =====================================
echo PIPELINE COMPLETED SUCCESSFULLY
echo =====================================
exit /b 0

:failure
echo.
echo PIPELINE FAILED. CHECK THE OUTPUT ABOVE.
exit /b 1
