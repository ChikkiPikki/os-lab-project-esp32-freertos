#ifndef TASK_MANAGER_H
#define TASK_MANAGER_H

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#define MAX_TASKS 32
#define MAX_SENSORS_PER_TASK 3
#define MAX_TASK_NAME_LEN 32

typedef enum {
    SENSOR_DHT11,
    SENSOR_ULTRASONIC,
    SENSOR_MPU6050,
    SENSOR_NONE
} sensor_type_t;

typedef struct {
    char name[MAX_TASK_NAME_LEN];
    int priority;
    int period_ms;
    sensor_type_t sensors[MAX_SENSORS_PER_TASK];
    int sensor_count;
} task_config_t;

// Initialize task manager and mutexes
void task_manager_init(void);

// Parse JSON config and create tasks dynamically
int task_manager_parse_and_create(const char *json_config);

// Stop all dynamic tasks
void task_manager_stop_all(void);

// UART logging with mutex
void uart_log(const char *task_name, const char *format, ...);

#endif // TASK_MANAGER_H
