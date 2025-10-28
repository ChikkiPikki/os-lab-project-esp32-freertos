#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/uart.h"
#include "task_manager.h"

#define TAG "MAIN"
#define UART_BUF_SIZE (4096)
#define UART_NUM UART_NUM_0

static void uart_init(void)
{
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    
    ESP_ERROR_CHECK(uart_param_config(UART_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM, UART_BUF_SIZE * 2, 0, 0, NULL, 0));
    
    ESP_LOGI(TAG, "UART initialized at 115200 baud");
}

static char* uart_read_json_config(void)
{
    ESP_LOGI(TAG, "Waiting for JSON config over UART...");
    ESP_LOGI(TAG, "Send START signal to begin config transfer");
    
    char *config_buffer = (char *)malloc(UART_BUF_SIZE);
    if (!config_buffer) {
        ESP_LOGE(TAG, "Failed to allocate config buffer");
        return NULL;
    }
    
    int total_len = 0;
    bool started = false;
    uint8_t data[128];
    
    while (1) {
        int len = uart_read_bytes(UART_NUM, data, sizeof(data) - 1, pdMS_TO_TICKS(100));
        if (len > 0) {
            data[len] = '\0';
            
            // Look for START signal
            if (!started) {
                if (strstr((char *)data, "START")) {
                    ESP_LOGI(TAG, "Received START signal, ready for config");
                    uart_write_bytes(UART_NUM, "READY\n", 6);
                    started = true;
                }
                continue;
            }
            
            // Look for END signal
            if (strstr((char *)data, "END")) {
                ESP_LOGI(TAG, "Received END signal, config complete");
                break;
            }
            
            // Accumulate data
            if (total_len + len < UART_BUF_SIZE - 1) {
                memcpy(config_buffer + total_len, data, len);
                total_len += len;
                config_buffer[total_len] = '\0';
            }
        }
    }
    
    if (total_len > 0) {
        ESP_LOGI(TAG, "Received %d bytes of config data", total_len);
        return config_buffer;
    }
    
    free(config_buffer);
    return NULL;
}

void app_main()
{
    ESP_LOGI(TAG, "=== Dynamic Task Manager Started ===");
    
    // Initialize UART for config reception
    uart_init();
    
    // Initialize task manager (creates mutexes, init sensors)
    task_manager_init();
    
    // Wait for JSON config from Python UI
    char *json_config = uart_read_json_config();
    
    if (json_config) {
        ESP_LOGI(TAG, "Parsing config and creating tasks...");
        
        int task_count = task_manager_parse_and_create(json_config);
        
        if (task_count > 0) {
            ESP_LOGI(TAG, "Successfully created %d tasks", task_count);
            uart_write_bytes(UART_NUM, "TASKS_CREATED\n", 14);
        } else {
            ESP_LOGE(TAG, "Failed to create tasks");
            uart_write_bytes(UART_NUM, "ERROR\n", 6);
        }
        
        free(json_config);
    } else {
        ESP_LOGE(TAG, "Failed to receive config");
        uart_write_bytes(UART_NUM, "ERROR\n", 6);
    }
    
    ESP_LOGI(TAG, "System running, tasks are active");
}
