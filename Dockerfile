# Use an official Python runtime as a parent image
FROM python:3.6

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in requirements.txt
RUN pip3.6 install -r requirements.txt

# Define environment variable
ENV SHARDS 7

# Run app.py when the container launches
CMD ["python3.6", "overseer.py", "production", "0", "6"]
# CMD ["python3.6", "dbot.py", "test"]