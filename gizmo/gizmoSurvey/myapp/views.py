from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.db import models
from django.utils import timezone
from .models import UserProfile, Survey, Question, SurveyResponse, Answer, Section
from .forms import UserRegistrationForm, SurveyForm, QuestionForm, SurveyResponseForm, SectionForm, QuestionBulkForm, SurveySettingsForm, AssignmentForm, SectionBulkForm
import json


def home(request):
    """Home page with login/signup options"""
    if request.user.is_authenticated:
        profile = UserProfile.objects.get(user=request.user)
        if profile.role == 'student':
            return redirect('student_dashboard')
        else:
            return redirect('teacher_dashboard')
    return render(request, 'myapp/home.html')


def custom_login(request):
    """Custom login view with show password functionality"""
    if request.user.is_authenticated:
        profile = UserProfile.objects.get(user=request.user)
        if profile.role == 'student':
            return redirect('student_dashboard')
        else:
            return redirect('teacher_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                profile = UserProfile.objects.get(user=user)
                if profile.role == 'student':
                    return redirect('student_dashboard')
                else:
                    return redirect('teacher_dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please fill in both username and password.')
    
    return render(request, 'myapp/login.html')


def custom_logout(request):
    """Custom logout view"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('home')


def register(request):
    """User registration with role selection"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('home')
    else:
        form = UserRegistrationForm()
    return render(request, 'myapp/register.html', {'form': form})


@login_required
def student_dashboard(request):
    """Student dashboard showing assigned surveys"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'student':
        messages.error(request, 'Access denied. Student access required.')
        return redirect('home')
    
    # Get surveys assigned to student's section
    assigned_surveys = Survey.objects.filter(
        sections=profile.section,
        is_active=True
    ).order_by('-created_at')
    
    # Check which surveys student has already completed
    completed_surveys = SurveyResponse.objects.filter(
        student=request.user
    ).values_list('survey_id', flat=True)
    
    context = {
        'assigned_surveys': assigned_surveys,
        'completed_surveys': completed_surveys,
        'profile': profile,
    }
    return render(request, 'myapp/student_dashboard.html', context)


@login_required
def take_survey(request, survey_id):
    """Student takes a survey"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'student':
        messages.error(request, 'Access denied. Student access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id)
    
    # Check if survey is assigned to student's section
    if profile.section not in survey.sections.all():
        messages.error(request, 'This survey is not assigned to your section.')
        return redirect('student_dashboard')
    
    # Check if survey is still open
    if not survey.is_open:
        messages.error(request, 'This survey is no longer accepting responses.')
        return redirect('student_dashboard')
    
    # Check if student already completed this survey
    if SurveyResponse.objects.filter(survey=survey, student=request.user).exists():
        messages.info(request, 'You have already completed this survey.')
        return redirect('student_dashboard')
    
    if request.method == 'POST':
        form = SurveyResponseForm(survey, request.POST)
        if form.is_valid():
            # Create survey response
            response = SurveyResponse.objects.create(
                survey=survey,
                student=request.user
            )
            
            # Save answers
            for question in survey.questions.all():
                field_name = f'question_{question.id}'
                if field_name in form.cleaned_data:
                    answer_value = form.cleaned_data[field_name]
                    
                    answer = Answer.objects.create(
                        response=response,
                        question=question
                    )
                    
                    if question.question_type in ['multiple_choice', 'likert_scale']:
                        answer.answer_choice = answer_value
                    elif question.question_type in ['short_answer', 'long_answer']:
                        answer.answer_text = answer_value
                    
                    answer.save()
            
            messages.success(request, 'Survey submitted successfully!')
            return redirect('student_dashboard')
    else:
        form = SurveyResponseForm(survey)
    
    context = {
        'survey': survey,
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/take_survey.html', context)


@login_required
def student_history(request):
    """Student's survey response history"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'student':
        messages.error(request, 'Access denied. Student access required.')
        return redirect('home')
    
    responses = SurveyResponse.objects.filter(student=request.user).order_by('-submitted_at')
    
    # Pagination
    paginator = Paginator(responses, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'profile': profile,
    }
    return render(request, 'myapp/student_history.html', context)


@login_required
def teacher_dashboard(request):
    """Teacher dashboard with survey management and analytics"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    # Get teacher's surveys
    surveys = Survey.objects.filter(created_by=request.user).order_by('-created_at')
    
    # Get response statistics with analytics data
    survey_stats = []
    active_surveys_count = 0
    total_responses_count = 0
    
    for survey in surveys:
        total_responses = survey.responses.count()
        total_responses_count += total_responses
        
        # Get analytics data for this survey
        analytics_data = get_survey_analytics_data(survey)
        
        # Count active surveys
        if survey.is_open:
            active_surveys_count += 1
        
        survey_stats.append({
            'survey': survey,
            'total_responses': total_responses,
            'is_open': survey.is_open,
            'analytics_data': analytics_data,
        })
    
    # Get dashboard analytics data
    dashboard_analytics = get_dashboard_analytics_data(request.user)
    
    context = {
        'survey_stats': survey_stats,
        'active_surveys_count': active_surveys_count,
        'total_responses_count': total_responses_count,
        'profile': profile,
        'dashboard_analytics': dashboard_analytics,
        'surveys_for_filter': surveys,
    }
    return render(request, 'myapp/teacher_dashboard.html', context)


@login_required
def create_survey(request):
    """Create a new survey"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            survey = form.save(commit=False)
            survey.created_by = request.user
            survey.save()
            form.save_m2m()  # Save many-to-many relationships
            messages.success(request, 'Survey created successfully!')
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = SurveyForm()
    
    context = {
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/create_survey.html', context)


@login_required
def edit_survey(request, survey_id):
    """Edit survey and manage questions"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'POST':
        form = SurveyForm(request.POST, instance=survey)
        if form.is_valid():
            form.save()
            messages.success(request, 'Survey updated successfully!')
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = SurveyForm(instance=survey)
    
    # Get questions for this survey
    questions = survey.questions.all().order_by('order')
    
    context = {
        'survey': survey,
        'form': form,
        'questions': questions,
        'profile': profile,
    }
    return render(request, 'myapp/edit_survey.html', context)


@login_required
def add_question(request, survey_id):
    """Add a question to a survey"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.survey = survey
            question.save()
            messages.success(request, 'Question added successfully!')
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = QuestionForm()
    
    context = {
        'survey': survey,
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/add_question.html', context)


@login_required
def edit_question(request, question_id):
    """Edit a question"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    question = get_object_or_404(Question, id=question_id, survey__created_by=request.user)
    
    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            messages.success(request, 'Question updated successfully!')
            return redirect('edit_survey', survey_id=question.survey.id)
    else:
        form = QuestionForm(instance=question)
    
    context = {
        'question': question,
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/edit_question.html', context)


@login_required
def delete_question(request, question_id):
    """Delete a question"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    question = get_object_or_404(Question, id=question_id, survey__created_by=request.user)
    survey_id = question.survey.id
    question.delete()
    messages.success(request, 'Question deleted successfully!')
    return redirect('edit_survey', survey_id=survey_id)


@login_required
def survey_responses(request, survey_id):
    """View survey responses"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    responses = SurveyResponse.objects.filter(survey=survey).order_by('-submitted_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        responses = responses.filter(
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__username__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(responses, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'survey': survey,
        'page_obj': page_obj,
        'search_query': search_query,
        'profile': profile,
    }
    return render(request, 'myapp/survey_responses.html', context)


@login_required
def view_response(request, response_id):
    """View individual response details"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    response = get_object_or_404(SurveyResponse, id=response_id, survey__created_by=request.user)
    answers = response.answers.all().order_by('question__order')
    
    context = {
        'response': response,
        'answers': answers,
        'profile': profile,
    }
    return render(request, 'myapp/view_response.html', context)


@login_required
def survey_analytics(request, survey_id):
    """Enhanced survey analytics and visualizations with real-time data"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    # Get comprehensive analytics data
    analytics_data = get_survey_analytics_data(survey)
    
    # Calculate survey statistics
    total_responses = survey.responses.count()
    total_questions = survey.questions.count()
    
    # Calculate completion rate by section
    section_stats = []
    for section in survey.sections.all():
        students_in_section = UserProfile.objects.filter(section=section, role='student').count()
        responses_from_section = SurveyResponse.objects.filter(
            survey=survey,
            student__userprofile__section=section
        ).count()
        
        completion_rate = (responses_from_section / students_in_section * 100) if students_in_section > 0 else 0
        
        section_stats.append({
            'section': section,
            'total_students': students_in_section,
            'responses_received': responses_from_section,
            'completion_rate': round(completion_rate, 1),
        })
    
    context = {
        'survey': survey,
        'analytics_data': analytics_data,
        'total_responses': total_responses,
        'total_questions': total_questions,
        'section_stats': section_stats,
        'profile': profile,
    }
    return render(request, 'myapp/survey_analytics.html', context)


def get_survey_analytics_data(survey):
    """Helper function to get comprehensive analytics data for a survey"""
    analytics_data = []
    
    for question in survey.questions.all():
        question_data = {
            'question': question,
            'type': question.question_type,
            'responses': [],
            'stats': {},
            'chart_data': {},
            'word_cloud_data': []
        }
        
        answers = Answer.objects.filter(response__survey=survey, question=question)
        
        if question.question_type == 'multiple_choice':
            # Count choices with percentages
            choice_counts = {}
            total_answers = answers.count()
            
            for answer in answers:
                choice = answer.answer_choice
                choice_counts[choice] = choice_counts.get(choice, 0) + 1
            
            # Calculate percentages
            choice_stats = {}
            for choice, count in choice_counts.items():
                percentage = (count / total_answers * 100) if total_answers > 0 else 0
                choice_stats[choice] = {
                    'count': count,
                    'percentage': round(percentage, 1)
                }
            
            question_data['stats'] = choice_stats
            question_data['chart_data'] = {
                'labels': list(choice_counts.keys()),
                'data': list(choice_counts.values()),
                'type': 'pie'
            }
        
        elif question.question_type == 'likert_scale':
            # Count scale values with percentages
            scale_counts = {}
            total_answers = answers.count()
            
            for answer in answers:
                value = answer.answer_choice
                scale_counts[value] = scale_counts.get(value, 0) + 1
            
            # Sort by scale value
            sorted_scales = sorted(scale_counts.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0])
            
            scale_stats = {}
            for value, count in sorted_scales:
                percentage = (count / total_answers * 100) if total_answers > 0 else 0
                scale_stats[value] = {
                    'count': count,
                    'percentage': round(percentage, 1)
                }
            
            question_data['stats'] = scale_stats
            question_data['chart_data'] = {
                'labels': [item[0] for item in sorted_scales],
                'data': [item[1] for item in sorted_scales],
                'type': 'bar'
            }
        
        elif question.question_type in ['short_answer', 'long_answer']:
            # Collect text responses for word cloud
            text_responses = [answer.answer_text.strip() for answer in answers if answer.answer_text and answer.answer_text.strip()]
            question_data['responses'] = text_responses
            
            # Process text for word cloud
            word_frequency = process_text_for_wordcloud(text_responses)
            question_data['word_cloud_data'] = word_frequency
        
        analytics_data.append(question_data)
    
    return analytics_data


def process_text_for_wordcloud(text_responses):
    """Process text responses to create word frequency data for word clouds"""
    import re
    from collections import Counter
    
    # Combine all text responses
    all_text = ' '.join(text_responses).lower()
    
    # Remove common stop words and clean text
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
        'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her',
        'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'very', 'really',
        'quite', 'just', 'only', 'also', 'too', 'so', 'as', 'if', 'when', 'where', 'why',
        'how', 'what', 'who', 'which', 'there', 'here', 'now', 'then', 'than', 'more',
        'most', 'some', 'any', 'all', 'both', 'each', 'every', 'no', 'not', 'yes'
    }
    
    # Extract words (alphanumeric characters only)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', all_text)
    
    # Filter out stop words and count frequency
    filtered_words = [word for word in words if word not in stop_words]
    word_counts = Counter(filtered_words)
    
    # Return top 50 words with their frequencies
    return [{'text': word, 'weight': count} for word, count in word_counts.most_common(50)]


@login_required
def student_response_details(request, response_id):
    """Get detailed response information for AJAX requests"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'student':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        response = SurveyResponse.objects.get(id=response_id, student=request.user)
        answers = response.answers.all().order_by('question__order')
        
        response_data = {
            'survey_title': response.survey.title,
            'submitted_at': response.submitted_at.strftime('%B %d, %Y at %I:%M %p'),
            'is_complete': response.is_complete,
            'answers': []
        }
        
        for answer in answers:
            answer_data = {
                'question_text': answer.question.question_text,
                'question_type': answer.question.question_type,
                'answer_value': '',
                'question_options': []
            }
            
            if answer.question.question_type == 'multiple_choice':
                answer_data['answer_value'] = answer.answer_choice
                answer_data['question_options'] = answer.question.options
            elif answer.question.question_type == 'likert_scale':
                answer_data['answer_value'] = answer.answer_choice
                answer_data['question_options'] = answer.question.likert_labels
                answer_data['likert_min'] = answer.question.likert_min
                answer_data['likert_max'] = answer.question.likert_max
            elif answer.question.question_type in ['short_answer', 'long_answer']:
                answer_data['answer_value'] = answer.answer_text
            
            response_data['answers'].append(answer_data)
        
        return JsonResponse(response_data)
    
    except SurveyResponse.DoesNotExist:
        return JsonResponse({'error': 'Response not found'}, status=404)


@login_required
def manage_sections(request):
    """Manage sections"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    sections = Section.objects.all().order_by('name')
    
    if request.method == 'POST':
        form = SectionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Section created successfully!')
            return redirect('manage_sections')
    else:
        form = SectionForm()
    
    context = {
        'sections': sections,
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/manage_sections.html', context)


# Enhanced CRUD Views for Survey Builder

@login_required
def question_bulk_operations(request, survey_id):
    """Handle bulk operations on questions"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'POST':
        form = QuestionBulkForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            question_ids = form.cleaned_data['question_ids'].split(',')
            questions = Question.objects.filter(id__in=question_ids, survey=survey)
            
            if action == 'delete':
                count = questions.count()
                questions.delete()
                messages.success(request, f'{count} questions deleted successfully!')
            
            elif action == 'reorder':
                new_order = form.cleaned_data['new_order']
                if new_order:
                    order_numbers = [int(x.strip()) for x in new_order.split(',') if x.strip()]
                    for i, question in enumerate(questions):
                        if i < len(order_numbers):
                            question.order = order_numbers[i]
                            question.save()
                    messages.success(request, 'Questions reordered successfully!')
            
            elif action == 'toggle_required':
                for question in questions:
                    question.is_required = not question.is_required
                    question.save()
                messages.success(request, 'Required status toggled successfully!')
            
            elif action == 'change_type':
                new_type = form.cleaned_data['new_type']
                if new_type:
                    questions.update(question_type=new_type)
                    messages.success(request, f'Question type changed to {new_type} successfully!')
            
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = QuestionBulkForm()
    
    context = {
        'survey': survey,
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/question_bulk_operations.html', context)


@login_required
def survey_settings_management(request, survey_id):
    """Enhanced survey settings management"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'POST':
        form = SurveySettingsForm(request.POST, instance=survey)
        if form.is_valid():
            form.save()
            messages.success(request, 'Survey settings updated successfully!')
            return redirect('survey_settings_management', survey_id=survey.id)
    else:
        form = SurveySettingsForm(instance=survey)
    
    # Get survey statistics
    stats = {
        'total_questions': survey.questions.count(),
        'total_responses': survey.responses.count(),
        'assigned_sections': survey.sections.count(),
        'is_open': survey.is_open,
        'days_until_due': None,
    }
    
    if survey.due_date:
        from datetime import datetime, timezone
        now = timezone.now()
        if survey.due_date > now:
            delta = survey.due_date - now
            stats['days_until_due'] = delta.days
    
    context = {
        'survey': survey,
        'form': form,
        'stats': stats,
        'profile': profile,
    }
    return render(request, 'myapp/survey_settings_management.html', context)


@login_required
def assignment_management(request, survey_id):
    """Manage survey assignments to sections"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'POST':
        form = AssignmentForm(request.POST)
        if form.is_valid():
            sections = form.cleaned_data['sections']
            due_date = form.cleaned_data['due_date']
            is_active = form.cleaned_data['is_active']
            
            # Update survey assignments
            survey.sections.set(sections)
            survey.due_date = due_date
            survey.is_active = is_active
            survey.save()
            
            messages.success(request, 'Survey assignments updated successfully!')
            return redirect('assignment_management', survey_id=survey.id)
    else:
        # Pre-populate form with current survey data
        form = AssignmentForm(initial={
            'sections': survey.sections.all(),
            'due_date': survey.due_date,
            'is_active': survey.is_active,
        })
    
    # Get assignment statistics
    assignment_stats = []
    for section in survey.sections.all():
        students_in_section = UserProfile.objects.filter(section=section, role='student').count()
        responses_from_section = SurveyResponse.objects.filter(
            survey=survey,
            student__userprofile__section=section
        ).count()
        
        assignment_stats.append({
            'section': section,
            'total_students': students_in_section,
            'responses_received': responses_from_section,
            'completion_rate': (responses_from_section / students_in_section * 100) if students_in_section > 0 else 0,
        })
    
    context = {
        'survey': survey,
        'form': form,
        'assignment_stats': assignment_stats,
        'profile': profile,
    }
    return render(request, 'myapp/assignment_management.html', context)


@login_required
def section_bulk_operations(request):
    """Handle bulk operations on sections"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    if request.method == 'POST':
        form = SectionBulkForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            section_ids = form.cleaned_data['section_ids'].split(',')
            sections = Section.objects.filter(id__in=section_ids)
            
            if action == 'delete':
                count = sections.count()
                sections.delete()
                messages.success(request, f'{count} sections deleted successfully!')
            
            elif action == 'activate':
                # For sections, we might want to activate/deactivate surveys assigned to them
                surveys = Survey.objects.filter(sections__in=sections)
                surveys.update(is_active=True)
                messages.success(request, f'Surveys assigned to selected sections activated!')
            
            elif action == 'deactivate':
                surveys = Survey.objects.filter(sections__in=sections)
                surveys.update(is_active=False)
                messages.success(request, f'Surveys assigned to selected sections deactivated!')
            
            return redirect('manage_sections')
    else:
        form = SectionBulkForm()
    
    sections = Section.objects.annotate(
        student_count=models.Count('userprofile', filter=models.Q(userprofile__role='student'))
    ).order_by('name')
    
    context = {
        'sections': sections,
        'form': form,
        'profile': profile,
    }
    return render(request, 'myapp/section_bulk_operations.html', context)


@login_required
def edit_section(request, section_id):
    """Edit a section"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    section = get_object_or_404(Section, id=section_id)
    
    if request.method == 'POST':
        form = SectionForm(request.POST, instance=section)
        if form.is_valid():
            form.save()
            messages.success(request, 'Section updated successfully!')
            return redirect('manage_sections')
    else:
        form = SectionForm(instance=section)
    
    # Get section statistics
    stats = {
        'total_students': UserProfile.objects.filter(section=section, role='student').count(),
        'total_surveys': Survey.objects.filter(sections=section).count(),
        'active_surveys': Survey.objects.filter(sections=section, is_active=True).count(),
    }
    
    context = {
        'section': section,
        'form': form,
        'stats': stats,
        'profile': profile,
    }
    return render(request, 'myapp/edit_section.html', context)


@login_required
def delete_section(request, section_id):
    """Delete a section"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        messages.error(request, 'Access denied. Teacher access required.')
        return redirect('home')
    
    section = get_object_or_404(Section, id=section_id)
    
    # Check if section has students or surveys
    students_count = UserProfile.objects.filter(section=section).count()
    surveys_count = Survey.objects.filter(sections=section).count()
    
    if students_count > 0 or surveys_count > 0:
        messages.error(request, f'Cannot delete section. It has {students_count} students and {surveys_count} surveys assigned.')
        return redirect('manage_sections')
    
    section.delete()
    messages.success(request, 'Section deleted successfully!')
    return redirect('manage_sections')


@login_required
def question_reorder(request, survey_id):
    """AJAX endpoint for reordering questions"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            question_orders = data.get('question_orders', [])
            
            for item in question_orders:
                question_id = item.get('question_id')
                new_order = item.get('order')
                
                question = Question.objects.get(id=question_id, survey=survey)
                question.order = new_order
                question.save()
            
            return JsonResponse({'success': True})
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def analytics_api(request, survey_id):
    """AJAX API endpoint for real-time analytics data"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
    
    if request.method == 'GET':
        try:
            # Get real-time analytics data
            analytics_data = get_survey_analytics_data(survey)
            
            # Calculate real-time statistics
            total_responses = survey.responses.count()
            total_questions = survey.questions.count()
            
            # Get recent responses (last 24 hours)
            from django.utils import timezone
            from datetime import timedelta
            recent_responses = SurveyResponse.objects.filter(
                survey=survey,
                submitted_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            # Section completion rates
            section_stats = []
            for section in survey.sections.all():
                students_in_section = UserProfile.objects.filter(section=section, role='student').count()
                responses_from_section = SurveyResponse.objects.filter(
                    survey=survey,
                    student__userprofile__section=section
                ).count()
                
                completion_rate = (responses_from_section / students_in_section * 100) if students_in_section > 0 else 0
                
                section_stats.append({
                    'section_name': section.name,
                    'section_code': section.code,
                    'total_students': students_in_section,
                    'responses_received': responses_from_section,
                    'completion_rate': round(completion_rate, 1),
                })
            
            return JsonResponse({
                'success': True,
                'data': {
                    'survey_id': survey.id,
                    'survey_title': survey.title,
                    'total_responses': total_responses,
                    'total_questions': total_questions,
                    'recent_responses': recent_responses,
                    'section_stats': section_stats,
                    'analytics_data': analytics_data,
                    'last_updated': timezone.now().isoformat(),
                }
            })
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


def get_dashboard_analytics_data(user):
    """Get comprehensive analytics data for the teacher dashboard"""
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    
    # Get all surveys by this teacher
    surveys = Survey.objects.filter(created_by=user)
    
    # Pie Chart Data - Response percentages per survey
    pie_chart_data = []
    for survey in surveys:
        total_responses = survey.responses.count()
        total_possible = 0
        
        # Calculate total possible responses (all students in assigned sections)
        for section in survey.sections.all():
            total_possible += UserProfile.objects.filter(section=section, role='student').count()
        
        response_percentage = (total_responses / total_possible * 100) if total_possible > 0 else 0
        
        pie_chart_data.append({
            'survey_id': survey.id,
            'survey_title': survey.title,
            'responses': total_responses,
            'possible': total_possible,
            'percentage': round(response_percentage, 1)
        })
    
    # Bar Chart Data - Responses per section
    sections = Section.objects.all()
    bar_chart_data = []
    
    for section in sections:
        response_count = SurveyResponse.objects.filter(
            student__userprofile__section=section,
            survey__created_by=user
        ).count()
        
        bar_chart_data.append({
            'section_id': section.id,
            'section_name': section.name,
            'section_code': section.code,
            'response_count': response_count
        })
    
    # Line Chart Data - Daily response trends (last 30 days)
    from django.utils import timezone
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    line_chart_data = []
    current_date = start_date
    
    while current_date <= end_date:
        daily_responses = SurveyResponse.objects.filter(
            survey__created_by=user,
            submitted_at__date=current_date
        ).count()
        
        line_chart_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'date_formatted': current_date.strftime('%m/%d'),
            'response_count': daily_responses
        })
        
        current_date += timedelta(days=1)
    
    # Check if data is empty
    has_data = {
        'surveys': surveys.exists(),
        'responses': SurveyResponse.objects.filter(survey__created_by=user).exists(),
        'sections': sections.exists(),
        'pie_chart': any(item['responses'] > 0 for item in pie_chart_data),
        'bar_chart': any(item['response_count'] > 0 for item in bar_chart_data),
        'line_chart': any(item['response_count'] > 0 for item in line_chart_data)
    }
    
    return {
        'pie_chart_data': pie_chart_data,
        'bar_chart_data': bar_chart_data,
        'line_chart_data': line_chart_data,
        'total_surveys': surveys.count(),
        'total_sections': sections.count(),
        'has_data': has_data
    }


@login_required
def dashboard_analytics_api(request):
    """AJAX API endpoint for dashboard analytics with filtering"""
    profile = UserProfile.objects.get(user=request.user)
    if profile.role != 'teacher':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'GET':
        try:
            # Get filter parameters
            survey_id = request.GET.get('survey_id')
            section_id = request.GET.get('section_id')
            date_from = request.GET.get('date_from')
            date_to = request.GET.get('date_to')
            
            # Base queryset for responses
            responses_query = SurveyResponse.objects.filter(survey__created_by=request.user)
            
            # Apply filters
            if survey_id and survey_id != 'all':
                responses_query = responses_query.filter(survey_id=survey_id)
            
            if section_id and section_id != 'all':
                responses_query = responses_query.filter(student__userprofile__section_id=section_id)
            
            if date_from:
                from datetime import datetime
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                responses_query = responses_query.filter(submitted_at__date__gte=date_from_obj)
            
            if date_to:
                from datetime import datetime
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                responses_query = responses_query.filter(submitted_at__date__lte=date_to_obj)
            
            # Get filtered analytics data
            filtered_analytics = get_filtered_dashboard_analytics(request.user, responses_query, survey_id, section_id, date_from, date_to)
            
            return JsonResponse({
                'success': True,
                'data': filtered_analytics
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


def get_filtered_dashboard_analytics(user, responses_query, survey_id=None, section_id=None, date_from=None, date_to=None):
    """Get filtered analytics data based on the provided filters"""
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    
    # Pie Chart Data - filtered by survey if specified
    surveys = Survey.objects.filter(created_by=user)
    if survey_id and survey_id != 'all':
        surveys = surveys.filter(id=survey_id)
    
    pie_chart_data = []
    for survey in surveys:
        # Filter responses for this survey
        survey_responses = responses_query.filter(survey=survey)
        total_responses = survey_responses.count()
        
        total_possible = 0
        # Calculate total possible responses
        sections_filter = survey.sections.all()
        if section_id and section_id != 'all':
            sections_filter = sections_filter.filter(id=section_id)
            
        for section in sections_filter:
            total_possible += UserProfile.objects.filter(section=section, role='student').count()
        
        response_percentage = (total_responses / total_possible * 100) if total_possible > 0 else 0
        
        pie_chart_data.append({
            'survey_id': survey.id,
            'survey_title': survey.title,
            'responses': total_responses,
            'possible': total_possible,
            'percentage': round(response_percentage, 1)
        })
    
    # Bar Chart Data - responses per section
    sections = Section.objects.all()
    if section_id and section_id != 'all':
        sections = sections.filter(id=section_id)
    
    bar_chart_data = []
    for section in sections:
        section_responses = responses_query.filter(student__userprofile__section=section)
        response_count = section_responses.count()
        
        bar_chart_data.append({
            'section_id': section.id,
            'section_name': section.name,
            'section_code': section.code,
            'response_count': response_count
        })
    
    # Line Chart Data - daily trends within date range
    from django.utils import timezone
    
    if date_from and date_to:
        start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
    else:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
    
    line_chart_data = []
    current_date = start_date
    
    while current_date <= end_date:
        daily_responses = responses_query.filter(submitted_at__date=current_date).count()
        
        line_chart_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'date_formatted': current_date.strftime('%m/%d'),
            'response_count': daily_responses
        })
        
        current_date += timedelta(days=1)
    
    # Check if filtered data is empty
    has_data = {
        'surveys': surveys.exists(),
        'responses': responses_query.exists(),
        'sections': sections.exists(),
        'pie_chart': any(item['responses'] > 0 for item in pie_chart_data),
        'bar_chart': any(item['response_count'] > 0 for item in bar_chart_data),
        'line_chart': any(item['response_count'] > 0 for item in line_chart_data)
    }
    
    return {
        'pie_chart_data': pie_chart_data,
        'bar_chart_data': bar_chart_data,
        'line_chart_data': line_chart_data,
        'has_data': has_data,
        'filters_applied': {
            'survey_id': survey_id,
            'section_id': section_id,
            'date_from': date_from,
            'date_to': date_to
        }
    }


@login_required
def reorder_questions(request, survey_id):
    """Handle AJAX request to reorder questions"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
    
    try:
        profile = UserProfile.objects.get(user=request.user)
        if profile.role != 'teacher':
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        survey = get_object_or_404(Survey, id=survey_id, created_by=request.user)
        
        # Parse JSON data
        data = json.loads(request.body)
        questions_data = data.get('questions', [])
        
        # Update question orders
        for question_data in questions_data:
            question_id = question_data.get('id')
            new_order = question_data.get('order')
            
            if question_id and new_order:
                question = get_object_or_404(Question, id=question_id, survey=survey)
                question.order = new_order
                question.save()
        
        return JsonResponse({'success': True, 'message': 'Question order updated successfully'})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

