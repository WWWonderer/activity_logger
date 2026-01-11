import queue
from new_logger.macos.macos_front_app_source import MacOSFrontAppSourceAdaptive

q = queue.Queue()

front_app = MacOSFrontAppSourceAdaptive()
front_app.IDLE_AFTER = 10
front_app.start(q.put) # press ctrl+c to stop

while not q.empty():
    item = q.get()
    print(item)