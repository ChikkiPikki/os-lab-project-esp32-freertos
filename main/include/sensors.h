

#ifndef SENSORS_H
#define SENSORS_H

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "board.h"

// Single read functions (existing)
int get_ultrasonic_data(SemaphoreHandle_t);
int get_dht11_data(SemaphoreHandle_t);
int initialize_mpu(SemaphoreHandle_t);
int get_mpu_acceleration_x();

// Averaged read functions (for dynamic tasks)
typedef struct {
    float dht_humidity;
    float dht_temperature;
    int ultrasonic_distance;
    float mpu_accel_x;
    float mpu_accel_y;
    float mpu_accel_z;
} sensor_readings_t;

int read_dht11_averaged(SemaphoreHandle_t handle, int samples, sensor_readings_t *out);
int read_ultrasonic_averaged(SemaphoreHandle_t handle, int samples, sensor_readings_t *out);
int read_mpu6050_averaged(SemaphoreHandle_t handle, int samples, sensor_readings_t *out);

#endif
