from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, Signal

from models.planner_models import PlannerTask, RepeatRule
from services.planner_storage import TaskRepository, ArchiveRepository


class TemplateService:
    """Операции с шаблонами активных задач."""

    def __init__(self, task_repo: TaskRepository, archive_repo: ArchiveRepository):
        self.task_repo = task_repo
        self.archive_repo = archive_repo

    def add_template(self, data: dict) -> PlannerTask:
        """
        Создаёт новый шаблон задачи на основе словаря data.
        Возвращает созданный объект.
        """
        task = PlannerTask(
            title=data["title"],
            description=data.get("description", ""),
            task_type=data.get("task_type", "one_time"),
            priority=data.get("priority", 3),
            repeat_rule=data.get("repeat_rule"),
            deadline=data.get("deadline"),
            deadline_duration=data.get("deadline_duration"),
            created_at=datetime.now(),
            is_template=True
        )
        # Если задача повторяющаяся, вычисляем следующую дату генерации
        if task.repeat_rule and task.repeat_rule.repeat_type != "none":
            task.next_generation_date = task.repeat_rule.next_occurrence(date.today())
        self.task_repo.add(task)
        return task

    def update_template(self, task_id: str, data: dict):
        """Обновляет шаблон задачи."""
        template = self.task_repo.get_by_id(task_id)
        if template is None or not template.is_template:
            return

        # Удаляем текущий активный экземпляр (безвозвратно)
        instances = self.task_repo.get_instances()
        for inst in instances:
            if inst.parent_id == task_id and inst.status == "active":
                self.task_repo.remove(inst.id)
                break

        # Применяем изменения
        template.title = data.get("title", template.title)
        template.description = data.get("description", template.description)
        template.priority = data.get("priority", template.priority)
        # Тип задачи менять нельзя (по требованию), но можно обновить другие поля
        # template.task_type = data.get("task_type", template.task_type)
        template.repeat_rule = data.get("repeat_rule", template.repeat_rule)
        template.deadline = data.get("deadline", template.deadline)
        template.deadline_duration = data.get("deadline_duration", template.deadline_duration)

        # Пересчитываем next_generation_date, если повторяющаяся
        if template.repeat_rule and template.repeat_rule.repeat_type != "none":
            template.next_generation_date = template.repeat_rule.next_occurrence(date.today())
        else:
            template.next_generation_date = None

        self.task_repo.update(task_id, template)

        # Если условия повторения выполняются сегодня, генерируем новый экземпляр
        if (template.repeat_rule and template.repeat_rule.repeat_type != "none"
                and template.next_generation_date == date.today()):
            instance = template.generate_instance()
            self.task_repo.add(instance)
            template.repeat_rule.occurrences_generated += 1
            template.next_generation_date = template.repeat_rule.next_occurrence(date.today())
            self.task_repo.update(task_id, template)

    def delete_template(self, task_id: str):
        """Перемещает шаблон в архив как удалённый, удаляет его экземпляр."""
        template = self.task_repo.get_by_id(task_id)
        if template is None or not template.is_template:
            return

        # Удаляем активный экземпляр
        instances = self.task_repo.get_instances()
        for inst in instances:
            if inst.parent_id == task_id and inst.status == "active":
                self.task_repo.remove(inst.id)
                break

        # Архивация шаблона
        template.mark_deleted_template()
        self.archive_repo.add(template)
        self.task_repo.remove(task_id)

    def toggle_pause(self, task_id: str):
        """Переключает паузу у шаблона."""
        template = self.task_repo.get_by_id(task_id)
        if template is None or not template.is_template:
            return
        template.toggle_pause()
        self.task_repo.update(task_id, template)


class ArchiveService:
    """Управление архивом задач."""

    def __init__(self, archive_repo: ArchiveRepository, task_repo: TaskRepository):
        self.archive_repo = archive_repo
        self.task_repo = task_repo

    def archive_completed(self, task: PlannerTask):
        """Архивирует выполненную задачу (одноразовую или экземпляр)."""
        task.mark_completed()
        self.archive_repo.add(task)
        self.task_repo.remove(task.id)

    def archive_deleted_template(self, task: PlannerTask):
        """Архивирует удалённый шаблон."""
        task.mark_deleted_template()
        self.archive_repo.add(task)
        self.task_repo.remove(task.id)

    def archive_expired_instance(self, task: PlannerTask):
        """Архивирует невыполненный экземпляр."""
        task.mark_expired_not_completed()
        self.archive_repo.add(task)
        self.task_repo.remove(task.id)

    def restore_deleted_template(self, task_id: str):
        """Восстанавливает удалённый шаблон из архива."""
        archived = self.archive_repo.get_by_id(task_id)
        if archived is None or archived.status != "deleted_template":
            return

        # Сбрасываем статус
        archived.status = "active"
        archived.archived_at = None
        archived.paused = False  # восстанавливаем без паузы

        self.task_repo.add(archived)
        self.archive_repo.remove(task_id)

    def delete_permanently(self, task_id: str):
        """Удаляет запись из архива безвозвратно."""
        self.archive_repo.remove(task_id)

    def create_copy_from_archived(self, task_id: str) -> dict | None:
        """Возвращает данные для создания копии архивной задачи."""
        archived = self.archive_repo.get_by_id(task_id)
        if archived is None:
            return None
        # Возвращаем словарь с полями, кроме служебных
        return {
            "title": archived.title,
            "description": archived.description,
            "priority": archived.priority,
            "repeat_rule": archived.repeat_rule.to_dict() if archived.repeat_rule else None,
            "deadline": archived.deadline.isoformat() if archived.deadline else None,
            "deadline_duration": archived.deadline_duration,
            "task_type": archived.task_type
        }

    def cleanup_expired(self):
        """Вызывает очистку устаревших записей в репозитории архива."""
        self.archive_repo.cleanup_expired()


class InstanceGenerator:
    """Генерация экземпляров из шаблонов."""

    def __init__(self, task_repo: TaskRepository, archive_repo: ArchiveRepository):
        self.task_repo = task_repo
        self.archive_repo = archive_repo

    def generate_for_date(self, current_date: date):
        """Создаёт экземпляры для всех подходящих шаблонов."""
        templates = self.task_repo.get_templates()
        for template in templates:
            if template.should_generate(current_date):
                # Создаём экземпляр
                instance = template.generate_instance()
                self.task_repo.add(instance)

                # Обновляем счётчик и следующую дату генерации
                template.repeat_rule.occurrences_generated += 1
                if template.repeat_rule.is_finished():
                    # Лимит исчерпан, архивируем шаблон как выполненный
                    template.mark_completed()
                    self.archive_repo.add(template)
                    self.task_repo.remove(template.id)
                else:
                    template.next_generation_date = template.repeat_rule.next_occurrence(current_date)
                    self.task_repo.update(template.id, template)


class PlannerFacade(QObject):
    """
    Координатор планировщика.
    Предоставляет интерфейс для UI и испускает сигналы об изменениях.
    """
    tasks_changed = Signal()
    archive_changed = Signal()
    instances_changed = Signal()

    def __init__(self, tasks_file="tasks.json", archive_file="archive.json"):
        super().__init__()
        self.task_repo = TaskRepository(tasks_file)
        self.archive_repo = ArchiveRepository(archive_file)

        self.template_service = TemplateService(self.task_repo, self.archive_repo)
        self.archive_service = ArchiveService(self.archive_repo, self.task_repo)
        self.instance_generator = InstanceGenerator(self.task_repo, self.archive_repo)

    def initialize(self):
        """Загрузка данных, очистка архива, генерация экземпляров."""
        self.archive_service.cleanup_expired()
        self.instance_generator.generate_for_date(date.today())
        self.tasks_changed.emit()
        self.archive_changed.emit()
        self.instances_changed.emit()

    # ---- Методы для UI ----
    def get_templates(self):
        return self.task_repo.get_templates()

    def get_today_instances(self):
        """Возвращает активные экземпляры, созданные сегодня."""
        today = date.today()
        instances = self.task_repo.get_instances()
        return [inst for inst in instances if inst.created_at.date() == today and inst.status == "active"]

    def get_archive(self, filters=None):
        return self.archive_repo.get_filtered(filters)

    def add_task(self, data):
        """Создаёт новый шаблон."""
        self.template_service.add_template(data)
        self.tasks_changed.emit()
        self.instances_changed.emit()

    def update_task(self, task_id, data):
        """Обновляет шаблон."""
        self.template_service.update_template(task_id, data)
        self.tasks_changed.emit()
        self.instances_changed.emit()

    def delete_template(self, task_id):
        """Удаляет шаблон."""
        self.template_service.delete_template(task_id)
        self.tasks_changed.emit()
        self.archive_changed.emit()
        self.instances_changed.emit()

    def toggle_pause(self, task_id):
        """Ставит/снимает паузу."""
        self.template_service.toggle_pause(task_id)
        self.tasks_changed.emit()

    def complete_task(self, task_id):
        """Выполняет задачу (одноразовую или экземпляр)."""
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            return
        if task.is_template:
            if task.task_type in ("one_time", "deadline"):
                self.archive_service.archive_completed(task)
                self.tasks_changed.emit()
                self.archive_changed.emit()
        else:
            self.archive_service.archive_completed(task)
            self.tasks_changed.emit()
            self.archive_changed.emit()
            self.instances_changed.emit()

    def restore_deleted_template(self, task_id):
        """Восстанавливает удалённый шаблон."""
        self.archive_service.restore_deleted_template(task_id)
        self.tasks_changed.emit()
        self.archive_changed.emit()

    def delete_from_archive(self, task_id):
        """Удаляет запись из архива безвозвратно."""
        self.archive_service.delete_permanently(task_id)
        self.archive_changed.emit()

    def get_copy_data(self, task_id):
        """Возвращает данные для копии архивной задачи."""
        return self.archive_service.create_copy_from_archived(task_id)