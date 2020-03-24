import argparse
import os
import sys
from CarlaWorld import CarlaWorld

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Settings for the data capture", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-wi', '--width', default=1024, type=int, help="camera rgb and depth sensor width in pixels")
    parser.add_argument('-he', '--height', default=768, type=int, help="camera rgb and depth sensor width in pixels")
    parser.add_argument('-ve', '--vehicles', default=100, type=int, help="number of vehicles to spawn in the simulation")
    parser.add_argument('-wa', '--walkers', default=110, type=int, help="number of walkers to spawn in the simulation")
    args = parser.parse_args()
    assert(args.width > 0 and args.height > 0)
    if args.vehicles == 0 and args.walkers == 0:
        print('Are you sure you don\'t want to spawn vehicles and pedestrians in the map?')

    # Sensor setup (rgb and depth share these values)
    # 1024 x 768 or 1920 x 1080 are recommended values. Higher values lead to better graphics but larger filesize
    sensor_width = args.width
    sensor_height = args.height
    fov = 90

    CarlaWorld = CarlaWorld()

    timestamps = []
    egos_to_run = 13
    print('Starting to record data...')
    CarlaWorld.spawn_npcs(number_of_vehicles=args.vehicles, number_of_walkers=args.walkers)
    for weather_option in CarlaWorld.weather_options:
        CarlaWorld.set_weather(weather_option)
        ego_vehicle_iteration = 0
        while ego_vehicle_iteration < egos_to_run:
            CarlaWorld.begin_data_acquisition(sensor_width, sensor_height, fov,
                                             frames_to_record_one_ego=2, timestamps=timestamps,
                                             egos_to_run=egos_to_run)
            print('Setting another vehicle as EGO.')
            ego_vehicle_iteration += 1

    CarlaWorld.remove_npcs()
    print('Finished simulation.')