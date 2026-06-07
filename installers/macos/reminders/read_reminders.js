// Kindle Dashboard —— 读取 macOS 提醒事项(JXA / JavaScript for Automation)
// 用法:osascript -l JavaScript read_reminders.js
// 输出:{updated_at, reminders:[{title, completed, list, dueDate, priority}], calendar_events:[]}
// 注:首次运行 macOS 会弹窗请求访问“提醒事项”,需点允许。
const app = Application("Reminders");
const lists = app.lists();
const reminders = [];

for (const list of lists) {
    const items = list.reminders();
    for (const item of items) {
        reminders.push({
            title: item.name(),
            completed: item.completed(),
            list: list.name(),
            dueDate: item.dueDate() ? item.dueDate().toISOString() : null,
            priority: item.priority()
        });
    }
}

JSON.stringify({
    updated_at: new Date().toISOString(),
    reminders: reminders,
    calendar_events: []
});
