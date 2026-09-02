{% with color_1_r=timer.color_1_rgb.0, color_1_g=timer.color_1_rgb.1, color_1_b=timer.color_1_rgb.2 %}
{% with color_2_r=timer.color_2_rgb.0, color_2_g=timer.color_2_rgb.1, color_2_b=timer.color_2_rgb.2 %}
{% with color_3_r=timer.color_3_rgb.0, color_3_g=timer.color_3_rgb.1, color_3_b=timer.color_3_rgb.2 %}
{% with delay_1=timer.delays.1, delay_2=timer.delays.2, delay_3=timer.delays.3 %}

var timer;
var timerColor;

function update_timer_values(clock_html, text_html, color) {
	$('#timer-wrapper').removeClass('d-none');
    $('#timer-clock').text(clock_html);
    $('#timer-text').text(text_html);
    timerColor = color;
    $('#timer').css('background-color', color);
}

function two_digits(n) {
	return ('0' + n).slice(-2);
}
function counter_string(dur) {
	dur = Math.max(0, dur);
	var seconds = dur % 60;
	dur = (dur - seconds) / 60;
	var minutes = dur % 60;
	dur = (dur - minutes) / 60;
	var hours = dur % 24;
	var days = (dur - hours) / 24;
	var counter = two_digits(hours) + ':' + two_digits(minutes) + ':' + two_digits(seconds);
	if (days > 0) {
		return days + '{{ _('d') }}' + ' ' + counter;
	}
	return counter;
}
function update_timer(local_delay) {
	local_date = new Date();
	local_time = Math.floor(local_date.getTime() / 1000);
	server_time = Math.floor(local_date.getTime() / 1000) + local_delay;
	server_date = new Date(server_time * 1000);
	clock_html = two_digits(server_date.getHours())+':'+two_digits(server_date.getMinutes())+':'+two_digits(server_date.getSeconds());
{% for timer_hour in timer.timer_hours %}
	if (server_time < {{ timer_hour.timestamp_1 }}) {
		color = 'rgb({{ color_1_r }}, {{ color_1_g }}, {{ color_1_b }})';
		text_html = '{{ timer_hour.text_before | replace ("'", "\\'") | safe }}'.replace('%s', counter_string({{ timer_hour.timestamp }} - server_time));
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (server_time < {{ timer_hour.timestamp_2 }}) {
		color_r = Math.floor({{ color_1_r }} + (server_time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_r - color_1_r }}));
		color_g = Math.floor({{ color_1_g }} + (server_time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_g - color_1_g }}));
		color_b = Math.floor({{ color_1_b }} + (server_time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_b - color_1_b }}));
		color = 'rgb(' + color_r + ', ' + color_g + ', ' + color_b + ')';
		text_html = '{{ timer_hour.text_before | replace ("'", "\\'") | safe }}'.replace('%s', counter_string({{ timer_hour.timestamp }} - server_time));
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (server_time < {{ timer_hour.timestamp_3 }}) {
		color_r = Math.floor({{ color_2_r }} + (server_time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_r - color_2_r }}));
		color_g = Math.floor({{ color_2_g }} + (server_time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_g - color_2_g }}));
		color_b = Math.floor({{ color_2_b }} + (server_time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_b - color_2_b }}));
		color = 'rgb(' + color_r + ', ' + color_g + ', ' + color_b + ')';
		text_html = '{{ timer_hour.text_before | replace ("'", "\\'") | safe }}'.replace('%s', counter_string({{ timer_hour.timestamp }} - server_time));
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (server_time < {{ timer_hour.timestamp_next }}) {
		color = 'rgb({{ color_3_r }}, {{ color_3_g }}, {{ color_3_b }})';
		text_html = '{{ timer_hour.text_after | replace ("'", "\\'") | safe }}'.replace('%s', counter_string(server_time - {{ timer_hour.timestamp }}));
		update_timer_values(clock_html, text_html, color);
		return;
	}
{% endfor %}
    $('#timer-wrapper').addClass('d-none');
}

$(document).ready(function(){
	now = new Date();
	local_time = Math.floor(now.getTime() / 1000);
    server_time = Math.floor({{ now }});
    local_delay = server_time - local_time;
    if (!timer) timer = setInterval('update_timer(' + local_delay + ');', 1000);
    update_timer(local_delay);
});

{% endwith %}
{% endwith %}
{% endwith %}
{% endwith %}
