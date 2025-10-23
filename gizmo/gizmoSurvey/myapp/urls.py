from django.urls import path
from . import views

urlpatterns = [
    # Home and authentication
    path('', views.home, name='home'),
    path('login/', views.custom_login, name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('register/', views.register, name='register'),
    
    # Student URLs
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('student/survey/<int:survey_id>/', views.take_survey, name='take_survey'),
    path('student/history/', views.student_history, name='student_history'),
    path('student/response/<int:response_id>/details/', views.student_response_details, name='student_response_details'),
    
    # Teacher URLs
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/survey/create/', views.create_survey, name='create_survey'),
    path('teacher/survey/<int:survey_id>/edit/', views.edit_survey, name='edit_survey'),
    path('teacher/survey/<int:survey_id>/question/add/', views.add_question, name='add_question'),
    path('teacher/question/<int:question_id>/edit/', views.edit_question, name='edit_question'),
    path('teacher/question/<int:question_id>/delete/', views.delete_question, name='delete_question'),
    path('teacher/survey/<int:survey_id>/responses/', views.survey_responses, name='survey_responses'),
    path('teacher/response/<int:response_id>/', views.view_response, name='view_response'),
    path('teacher/survey/<int:survey_id>/analytics/', views.survey_analytics, name='survey_analytics'),
    path('teacher/survey/<int:survey_id>/analytics/api/', views.analytics_api, name='analytics_api'),
    path('teacher/dashboard/analytics/api/', views.dashboard_analytics_api, name='dashboard_analytics_api'),
    path('teacher/sections/', views.manage_sections, name='manage_sections'),
    
    # Enhanced CRUD URLs for Survey Builder
    path('teacher/survey/<int:survey_id>/questions/bulk/', views.question_bulk_operations, name='question_bulk_operations'),
    path('teacher/survey/<int:survey_id>/settings/', views.survey_settings_management, name='survey_settings_management'),
    path('teacher/survey/<int:survey_id>/assignments/', views.assignment_management, name='assignment_management'),
    path('teacher/sections/bulk/', views.section_bulk_operations, name='section_bulk_operations'),
    path('teacher/section/<int:section_id>/edit/', views.edit_section, name='edit_section'),
    path('teacher/section/<int:section_id>/delete/', views.delete_section, name='delete_section'),
    path('teacher/survey/<int:survey_id>/questions/reorder/', views.reorder_questions, name='reorder_questions'),
]