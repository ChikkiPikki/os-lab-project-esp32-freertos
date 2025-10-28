#include "sensors.h"
#include "dht.h"
#include "mpu6050.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "esp_timer.h"

static const char *TAG_MPU = "MPU";
static mpu6050_dev_t s_mpu_dev = {0};
static bool s_mpu_inited = false;

int get_ultrasonic_data(SemaphoreHandle_t handle)
{
    static bool pins_inited = false;
    if (handle) xSemaphoreTake(handle, portMAX_DELAY);

    if (!pins_inited)
    {
        gpio_reset_pin(ULTRASONIC_TRIG_PIN);
        gpio_reset_pin(ULTRASONIC_ECHO_PIN);
        gpio_set_direction(ULTRASONIC_TRIG_PIN, GPIO_MODE_OUTPUT);
        gpio_set_level(ULTRASONIC_TRIG_PIN, 0);
        gpio_set_direction(ULTRASONIC_ECHO_PIN, GPIO_MODE_INPUT);
        pins_inited = true;
    }

    // Send 10us pulse on TRIG
    gpio_set_level(ULTRASONIC_TRIG_PIN, 0);
    esp_rom_delay_us(2);
    gpio_set_level(ULTRASONIC_TRIG_PIN, 1);
    esp_rom_delay_us(10);
    gpio_set_level(ULTRASONIC_TRIG_PIN, 0);

    // Wait for ECHO to go high (max 30 ms)
    int timeout_us = 30000;
    int waited = 0;
    while (gpio_get_level(ULTRASONIC_ECHO_PIN) == 0 && waited < timeout_us)
    {
        esp_rom_delay_us(1);
        waited++;
    }
    if (waited >= timeout_us)
    {
        if (handle) xSemaphoreGive(handle);
        return -1;
    }

    // Measure high pulse width up to 30 ms
    int duration_us = 0;
    while (gpio_get_level(ULTRASONIC_ECHO_PIN) == 1 && duration_us < timeout_us)
    {
        esp_rom_delay_us(1);
        duration_us++;
    }

    if (handle) xSemaphoreGive(handle);

    if (duration_us <= 0 || duration_us >= timeout_us)
        return -1;

    // Convert time to distance in cm (HC-SR04: distance(cm) = duration_us / 58)
    int distance_cm = duration_us / 58;
    return distance_cm;
}

int get_dht11_data(SemaphoreHandle_t handle)
{   
    xSemaphoreTake(handle, portMAX_DELAY);
    int16_t humidity, temperature;
    esp_err_t err = dht_read_data(DHT_SENSOR_TYPE, DHT_DATA_PIN, &humidity, &temperature);
    if (err == ESP_OK) {
        ESP_LOGI("DHT", "humidity=%d tenth%% temp=%d tenthC", humidity, temperature);
    } else {
        ESP_LOGE("DHT", "dht_read_data failed: %s", esp_err_to_name(err));
        xSemaphoreGive(handle);
        return -1;
    }
    xSemaphoreGive(handle);
    return humidity;
}

int initialize_mpu(SemaphoreHandle_t handle)
{
    if (s_mpu_inited) return 0;
    if (handle) xSemaphoreTake(handle, portMAX_DELAY);

    esp_err_t err;
    err = mpu6050_init_desc(&s_mpu_dev, MPU6050_I2C_ADDRESS_LOW, 0, MPU_SDA_PIN, MPU_SCL_PIN);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MPU, "init_desc failed: %s", esp_err_to_name(err));
        if (handle) xSemaphoreGive(handle);
        return -1;
    }

    err = mpu6050_init(&s_mpu_dev);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MPU, "mpu6050_init failed: %s", esp_err_to_name(err));
        if (handle) xSemaphoreGive(handle);
        return -1;
    }

    s_mpu_inited = true;
    if (handle) xSemaphoreGive(handle);
    ESP_LOGI(TAG_MPU, "MPU6050 initialized");
    return 0;
}

int get_mpu_acceleration_x()
{
    if (!s_mpu_inited) return 0;
    mpu6050_acceleration_t accel = {0};
    mpu6050_rotation_t rot = {0};
    float temp = 0;
    esp_err_t err;

    err = mpu6050_get_temperature(&s_mpu_dev, &temp);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MPU, "temp read failed: %s", esp_err_to_name(err));
        return 0;
    }
    err = mpu6050_get_motion(&s_mpu_dev, &accel, &rot);
    if (err != ESP_OK) {
        ESP_LOGE(TAG_MPU, "motion read failed: %s", esp_err_to_name(err));
        return 0;
    }
    ESP_LOGI(TAG_MPU, "Accel(g): x=%.3f y=%.3f z=%.3f, Gyro(dps): x=%.1f y=%.1f z=%.1f, T=%.1fC", accel.x, accel.y, accel.z, rot.x, rot.y, rot.z, temp);
    return (int)(accel.x * 1000.0f);
}

// Averaged sensor reading functions
int read_dht11_averaged(SemaphoreHandle_t handle, int samples, sensor_readings_t *out)
{
    if (!out || samples <= 0) return -1;
    
    float sum_hum = 0, sum_temp = 0;
    int valid_count = 0;
    
    for (int i = 0; i < samples; i++) {
        xSemaphoreTake(handle, portMAX_DELAY);
        int16_t humidity, temperature;
        esp_err_t err = dht_read_data(DHT_SENSOR_TYPE, DHT_DATA_PIN, &humidity, &temperature);
        xSemaphoreGive(handle);
        
        if (err == ESP_OK) {
            sum_hum += humidity / 10.0f;  // Convert to actual percentage
            sum_temp += temperature / 10.0f;  // Convert to actual Celsius
            valid_count++;
        }
        if (i < samples - 1) vTaskDelay(pdMS_TO_TICKS(100)); // Small delay between reads
    }
    
    if (valid_count == 0) return -1;
    
    out->dht_humidity = sum_hum / valid_count;
    out->dht_temperature = sum_temp / valid_count;
    return 0;
}

int read_ultrasonic_averaged(SemaphoreHandle_t handle, int samples, sensor_readings_t *out)
{
    if (!out || samples <= 0) return -1;
    
    int sum_dist = 0;
    int valid_count = 0;
    
    for (int i = 0; i < samples; i++) {
        int dist = get_ultrasonic_data(handle);
        if (dist > 0) {
            sum_dist += dist;
            valid_count++;
        }
        if (i < samples - 1) vTaskDelay(pdMS_TO_TICKS(50)); // Small delay between reads
    }
    
    if (valid_count == 0) return -1;
    
    out->ultrasonic_distance = sum_dist / valid_count;
    return 0;
}

int read_mpu6050_averaged(SemaphoreHandle_t handle, int samples, sensor_readings_t *out)
{
    if (!out || samples <= 0 || !s_mpu_inited) return -1;
    
    float sum_x = 0, sum_y = 0, sum_z = 0;
    int valid_count = 0;
    
    for (int i = 0; i < samples; i++) {
        mpu6050_acceleration_t accel = {0};
        mpu6050_rotation_t rot = {0};
        
        if (handle) xSemaphoreTake(handle, portMAX_DELAY);
        esp_err_t err = mpu6050_get_motion(&s_mpu_dev, &accel, &rot);
        if (handle) xSemaphoreGive(handle);
        
        if (err == ESP_OK) {
            sum_x += accel.x;
            sum_y += accel.y;
            sum_z += accel.z;
            valid_count++;
        }
        if (i < samples - 1) vTaskDelay(pdMS_TO_TICKS(10)); // Small delay between reads
    }
    
    if (valid_count == 0) return -1;
    
    out->mpu_accel_x = sum_x / valid_count;
    out->mpu_accel_y = sum_y / valid_count;
    out->mpu_accel_z = sum_z / valid_count;
    return 0;
}