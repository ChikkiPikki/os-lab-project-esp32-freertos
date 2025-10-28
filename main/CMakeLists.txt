 idf_component_register(
     SRCS
         "main.c" "sensors.c" "task_manager.c"
     INCLUDE_DIRS
         "include"
     REQUIRES
         driver
         esp_timer
         nvs_flash
         dht
         mpu6050
         i2cdev
         json
 )
