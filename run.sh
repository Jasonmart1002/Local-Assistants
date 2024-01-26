#!/bin/bash

# Define the name of the Conda environment
CONDA_ENV_NAME="Local-Assistants"

# Step 1: Activate the Conda environment
echo "Activating Conda environment..."
conda activate "$CONDA_ENV_NAME"

# Step 2: Export environment variable
export OPENAI_API_KEY=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
export SECRET_KEY=something-secret-123

# Step 3: Install requirements
if [ $FIRST_RUN == true ]; then
    echo "Installing requirements..."
    pip install -r requirements.txt
fi

# Step 4: Export environment variable
export OPENAI_API_KEY=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
export SECRET_KEY=something-secret-123

# Step 5: Message about openai migrate
if [ $FIRST_RUN == true ]; then
    echo "Please run 'openai migrate' to migrate your codebase"
    openai migrate
fi

# Step 6: Run Flask app
echo "Starting Flask app at http://localhost:5000"
FLASK_APP=app FLASK_ENV=development flask run --reload 

