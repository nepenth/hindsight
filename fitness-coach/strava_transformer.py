#!/usr/bin/env python3
"""
Transform Strava activities into fitness coach workout format.
"""
from datetime import datetime
from typing import Dict, List

# Strava activity type to workout type mapping
ACTIVITY_TYPE_MAP = {
    "Run": "cardio",
    "Ride": "cardio",
    "Swim": "cardio",
    "Walk": "cardio",
    "Hike": "cardio",
    "VirtualRide": "cardio",
    "VirtualRun": "cardio",
    "Workout": "strength",
    "WeightTraining": "strength",
    "Crossfit": "strength",
    "Yoga": "yoga",
    "Pilates": "yoga",
    "Rowing": "cardio",
    "Elliptical": "cardio",
    "StairStepper": "cardio",
    "IceSkate": "cardio",
    "RollerSki": "cardio",
    "Skateboard": "cardio",
    "InlineSkate": "cardio",
    "Snowboard": "cardio",
    "Snowshoe": "cardio",
    "AlpineSki": "cardio",
    "BackcountrySki": "cardio",
    "NordicSki": "cardio",
    "RockClimbing": "strength",
    "Handcycle": "cardio",
    "Wheelchair": "cardio",
}

# Intensity mapping based on average heart rate zones (if available)
def calculate_intensity(activity: Dict) -> str:
    """
    Calculate workout intensity from activity data.

    Uses heart rate zones if available, otherwise estimated from pace/speed.
    """
    # If we have heart rate data
    if activity.get("has_heartrate") and activity.get("average_heartrate"):
        avg_hr = activity["average_heartrate"]

        # Rough zones (user could customize based on their max HR)
        if avg_hr < 120:
            return "low"
        elif avg_hr < 150:
            return "moderate"
        else:
            return "high"

    # Fallback: use perceived exertion or default to moderate
    return "moderate"


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_distance(meters: float) -> str:
    """Format distance in meters to km with 2 decimals."""
    km = meters / 1000
    return f"{km:.2f}km"


def format_pace(activity: Dict) -> str:
    """Calculate and format pace (min/km) for runs."""
    if activity.get("distance") and activity.get("moving_time"):
        distance_km = activity["distance"] / 1000
        time_minutes = activity["moving_time"] / 60
        pace = time_minutes / distance_km
        pace_min = int(pace)
        pace_sec = int((pace - pace_min) * 60)
        return f"{pace_min}:{pace_sec:02d}/km"
    return None


def format_speed(activity: Dict) -> str:
    """Calculate and format average speed (km/h) for cycling."""
    if activity.get("distance") and activity.get("moving_time"):
        distance_km = activity["distance"] / 1000
        time_hours = activity["moving_time"] / 3600
        speed = distance_km / time_hours
        return f"{speed:.1f}km/h"
    return None


def transform_activity(activity: Dict) -> Dict:
    """
    Transform a Strava activity into workout memory format.

    Args:
        activity: Strava activity dictionary

    Returns:
        Formatted workout data ready for logging
    """
    # Basic info
    activity_type = activity.get("type", "Workout")
    workout_type = ACTIVITY_TYPE_MAP.get(activity_type, "other")
    name = activity.get("name", "Untitled Workout")

    # Time and duration
    duration_seconds = activity.get("moving_time", 0)
    duration_minutes = duration_seconds // 60
    start_date = activity.get("start_date")

    # Distance and metrics
    distance_meters = activity.get("distance", 0)
    elevation_gain = activity.get("total_elevation_gain", 0)
    avg_hr = activity.get("average_heartrate")

    # Calculate intensity
    intensity = calculate_intensity(activity)

    # Build workout description
    description_parts = [
        f"User completed {activity_type.lower()}"
    ]

    # Add distance if available
    if distance_meters > 0:
        description_parts.append(f": {format_distance(distance_meters)}")

    description_parts.append(f" in {format_duration(duration_seconds)}")

    # Add pace/speed for relevant activities
    if activity_type == "Run" and distance_meters > 0:
        pace = format_pace(activity)
        if pace:
            description_parts.append(f" at {pace} pace")

    elif activity_type in ["Ride", "VirtualRide"] and distance_meters > 0:
        speed = format_speed(activity)
        if speed:
            description_parts.append(f" at {speed}")

    # Add elevation if significant
    if elevation_gain > 50:
        description_parts.append(f" with {int(elevation_gain)}m elevation gain")

    # Add heart rate if available
    if avg_hr:
        description_parts.append(f", avg HR {int(avg_hr)}bpm")

    description = "".join(description_parts) + "."

    # Add workout name as context if meaningful
    notes = f"Strava activity: {name}"

    # Build exercises list
    exercises = [activity_type.lower()]
    if "workout_type" in activity:
        workout_type_id = activity["workout_type"]
        # Map workout types (run-specific)
        run_types = {
            0: "default run",
            1: "race",
            2: "long run",
            3: "intervals",
            4: "tempo"
        }
        if workout_type_id in run_types:
            exercises.append(run_types[workout_type_id])
            notes += f" ({run_types[workout_type_id]})"

    return {
        "content": description,
        "workout_type": workout_type,
        "duration_minutes": duration_minutes,
        "exercises": exercises,
        "intensity": intensity,
        "notes": notes,
        "event_date": start_date,
        "raw_activity": {
            "distance_meters": distance_meters,
            "elevation_gain": elevation_gain,
            "average_heartrate": avg_hr,
            "strava_id": activity.get("id"),
            "strava_type": activity_type,
        }
    }


def transform_activities(activities: List[Dict]) -> List[Dict]:
    """
    Transform multiple Strava activities.

    Args:
        activities: List of Strava activity dictionaries

    Returns:
        List of formatted workout data
    """
    return [transform_activity(activity) for activity in activities]


def get_activity_summary(activities: List[Dict]) -> Dict:
    """
    Generate a summary of activities.

    Args:
        activities: List of Strava activities

    Returns:
        Summary statistics
    """
    if not activities:
        return {}

    total_distance = sum(a.get("distance", 0) for a in activities) / 1000  # km
    total_time = sum(a.get("moving_time", 0) for a in activities) / 3600  # hours
    total_elevation = sum(a.get("total_elevation_gain", 0) for a in activities)

    # Count by type
    type_counts = {}
    for activity in activities:
        activity_type = activity.get("type", "Unknown")
        type_counts[activity_type] = type_counts.get(activity_type, 0) + 1

    # Date range
    dates = [datetime.fromisoformat(a["start_date"].replace("Z", "+00:00"))
             for a in activities if "start_date" in a]
    oldest = min(dates) if dates else None
    newest = max(dates) if dates else None

    return {
        "total_activities": len(activities),
        "total_distance_km": round(total_distance, 1),
        "total_time_hours": round(total_time, 1),
        "total_elevation_m": int(total_elevation),
        "activity_types": type_counts,
        "date_range": {
            "oldest": oldest.strftime("%Y-%m-%d") if oldest else None,
            "newest": newest.strftime("%Y-%m-%d") if newest else None,
        }
    }
