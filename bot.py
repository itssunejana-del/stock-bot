def auto_request_stock():
    """Автоматически запрашивает сток каждую минуту"""
    logger.info("🤖 Запускаю автоматические запросы стока...")
    
    while True:
        try:
            # Сначала отправляем /start боту
            logger.info("🔄 Отправляю /start боту...")
            success_start = send_to_garden_bot("/start")
            time.sleep(3)  # Ждем ответа бота
            
            # Затем запрашиваем сток
            logger.info("🔄 Отправляю '🌱 Сток'...")
            success_stock = send_to_garden_bot("🌱 Сток")
            
            if success_start and success_stock:
                logger.info("✅ Обе команды отправлены успешно")
            else:
                logger.error("❌ Ошибка отправки команд")
                
        except Exception as e:
            logger.error(f"❌ Ошибка автоматического запроса: {e}")
            
        time.sleep(60)  # Каждую минуту
