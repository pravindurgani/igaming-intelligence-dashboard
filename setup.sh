#!/bin/bash
# Streamlit Cloud setup script
# This script runs automatically during deployment to download the spaCy model

python -m spacy download en_core_web_sm
