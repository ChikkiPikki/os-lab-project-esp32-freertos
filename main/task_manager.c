#include "task_manager.h"
#include "sensors.h"
#include "board.h"
#include "esp_log.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "i2cdev.h"
#include "cJSON.h"
#include <string.h>
#include <stdarg.h>

static const char *TAG = "TaskManager";

// Global mutexes for sensors
static SemaphoreHandle_t dht_mutex = NULL;
static SemaphoreHandle_t ultrasonic_mutex = NULL;
static SemaphoreHandle_t mpu_mutex = NULL;
static SemaphoreHandle_t uart_mutex = NULL;

// Track created tasks
static TaskHandle_t task_handles[MAX_TASKS] = {0};
static int active_task_count = 0;

// Task function that reads sensors and logs via UART
static void dynamic_sensor_task(void *pvParameters)
{
    task_config_t *config = (task_config_t *)pvParameters;
    sensor_readings_t readings = {0};
    
    char log_buffer[256];
    
    while (1) {
        TickType_t start = xTaskGetTickCount();
        
        // Clear readings
        memset(&readings, 0, sizeof(readings));
        
        // Read all configured sensors with averaging (10 samples)
        int success = 1;
        for (int i = 0; i < config->sensor_count; i++) {
            switch (config->sensors[i]) {
                case SENSOR_DHT11:
                    if (read_dht11_averaged(dht_mutex, 10, &readings) != 0) {
                        success = 0;
                    }
                    break;
                case SENSOR_ULTRASONIC:
                    if (read_ultrasonic_averaged(ultrasonic_mutex, 10, &readings) != 0) {
                        success = 0;
                    }
                    break;
                case SENSOR_MPU6050:
                    if (read_mpu6050_averaged(mpu_mutex, 10, &readings) != 0) {
                        success = 0;
                    }
                    break;
                default:
                    break;
            }
        }
        
        // Log results via UART
        if (success) {
            snprintf(log_buffer, sizeof(log_buffer),
                     "[%s] H:%.1f%% T:%.1fC Dist:%dcm AccX:%.3fg AccY:%.3fg AccZ:%.3fg\n",
                     config->name,
                     readings.dht_humidity,
                     readings.dht_temperature,
                     readings.ultrasonic_distance,
                     readings.mpu_accel_x,
                     readings.mpu_accel_y,
                     readings.mpu_accel_z);
            uart_log(config->name, "%s", log_buffer);
        } else {
            uart_log(config->name, "Read error\n");
        }
        
        vTaskDelayUntil(&start, pdMS_TO_TICKS(config->period_ms));
    }
}

void task_manager_init(void)
{
    // Create sensor mutexes
    dht_mutex = xSemaphoreCreateMutex();
    ultrasonic_mutex = xSemaphoreCreateMutex();
    mpu_mutex = xSemaphoreCreateMutex();
    uart_mutex = xSemaphoreCreateMutex();
    
    // Initialize sensors
    gpio_set_pull_mode(DHT_DATA_PIN, GPIO_PULLUP_ONLY);
    vTaskDelay(pdMS_TO_TICKS(2000)); // DHT stabilization
    
    // Initialize I2C for MPU6050
    ESP_ERROR_CHECK(i2cdev_init());
    initialize_mpu(mpu_mutex);
    
    ESP_LOGI(TAG, "Task manager initialized");
}

static sensor_type_t parse_sensor_type(const char *sensor_str)
{
    if (strcmp(sensor_str, "dht11") == 0) return SENSOR_DHT11;
    if (strcmp(sensor_str, "ultrasonic") == 0) return SENSOR_ULTRASONIC;
    if (strcmp(sensor_str, "mpu6050") == 0) return SENSOR_MPU6050;
    return SENSOR_NONE;
}

int task_manager_parse_and_create(const char *json_config)
{
    if (!json_config) return -1;
    
    cJSON *root = cJSON_Parse(json_config);
    if (!root) {
        ESP_LOGE(TAG, "JSON parse error");
        return -1;
    }
    
    cJSON *tasks_array = cJSON_GetObjectItem(root, "tasks");
    if (!cJSON_IsArray(tasks_array)) {
        ESP_LOGE(TAG, "Invalid tasks array");
        cJSON_Delete(root);
        return -1;
    }
    
    int task_count = cJSON_GetArraySize(tasks_array);
    if (task_count > MAX_TASKS) {
        ESP_LOGW(TAG, "Task count %d exceeds max %d, truncating", task_count, MAX_TASKS);
        task_count = MAX_TASKS;
    }
    
    ESP_LOGI(TAG, "Creating %d tasks", task_count);
    
    for (int i = 0; i < task_count; i++) {
        cJSON *task_json = cJSON_GetArrayItem(tasks_array, i);
        if (!task_json) continue;
        
        // Allocate config structure (persists for task lifetime)
        task_config_t *config = (task_config_t *)malloc(sizeof(task_config_t));
        if (!config) {
            ESP_LOGE(TAG, "Failed to allocate task config");
            continue;
        }
        
        memset(config, 0, sizeof(task_config_t));
        
        // Parse task properties
        cJSON *name = cJSON_GetObjectItem(task_json, "name");
        cJSON *priority = cJSON_GetObjectItem(task_json, "priority");
        cJSON *period = cJSON_GetObjectItem(task_json, "period_ms");
        cJSON *sensors = cJSON_GetObjectItem(task_json, "sensors");
        
        if (!name || !priority || !period || !sensors) {
            ESP_LOGE(TAG, "Missing required task fields");
            free(config);
            continue;
        }
        
        strncpy(config->name, name->valuestring, MAX_TASK_NAME_LEN - 1);
        config->priority = priority->valueint;
        config->period_ms = period->valueint;
        
        // Parse sensors
        int sensor_count = cJSON_GetArraySize(sensors);
        config->sensor_count = (sensor_count > MAX_SENSORS_PER_TASK) ? MAX_SENSORS_PER_TASK : sensor_count;
        
        for (int j = 0; j < config->sensor_count; j++) {
            cJSON *sensor = cJSON_GetArrayItem(sensors, j);
            if (sensor && sensor->valuestring) {
                config->sensors[j] = parse_sensor_type(sensor->valuestring);
            }
        }
        
        // Create the task
        BaseType_t ret = xTaskCreate(
            dynamic_sensor_task,
            config->name,
            4096,
            (void *)config,
            config->priority,
            &task_handles[active_task_count]
        );
        
        if (ret == pdPASS) {
            ESP_LOGI(TAG, "Created task: %s (priority=%d, period=%dms, sensors=%d)",
                     config->name, config->priority, config->period_ms, config->sensor_count);
            active_task_count++;
        } else {
            ESP_LOGE(TAG, "Failed to create task: %s", config->name);
            free(config);
        }
    }
    
    cJSON_Delete(root);
    return active_task_count;
}

void task_manager_stop_all(void)
{
    for (int i = 0; i < active_task_count; i++) {
        if (task_handles[i]) {
            vTaskDelete(task_handles[i]);
            task_handles[i] = NULL;
        }
    }
    active_task_count = 0;
    ESP_LOGI(TAG, "All tasks stopped");
}

void uart_log(const char *task_name, const char *format, ...)
{
    if (!uart_mutex) return;
    
    xSemaphoreTake(uart_mutex, portMAX_DELAY);
    
    char buffer[256];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    
    // Send to UART0 (connected to USB)
    uart_write_bytes(UART_NUM_0, buffer, strlen(buffer));
    
    xSemaphoreGive(uart_mutex);
}
