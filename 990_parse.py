import re
import webbrowser
import pandas as pd
from bs4 import BeautifulSoup
from utilities.helpers import prep_request, makedirs, write_file

source = 'data_source.csv' # csv file with one column: source
html_filename = 'test.html'
show_board = "Yes" 
show_staff = "Yes"

df_orgs = pd.DataFrame(columns=['org_id', 'ein', 'org_name', 'year', 'voting_members', 'employees', 'total_revenue', 'salaries', 'total_expenses', 'rev_minus_exp', 'assets', 'highest_comp_name', 'highest_comp_title', 'highest_comp_amount'])
df_people = pd.DataFrame(columns=['org_id', 'org_name', 'year', 'name', 'role', 'job_title', 'comp', 'reportable_comp', 'other_comp', 'total_comp'])
df_report = pd.DataFrame(columns=['org_id', 'summary_text'])

def str_to_int(conv, na): 
	try:
		new_value = int(conv)
	except:
		if na == "number":
			new_value = 0
		if na == "text":
			new_value = "na"

	return new_value

with open(source) as input:
	df_source = pd.read_csv(input)

source_urls = df_source.source.unique()

for su in source_urls:
	summary_text = ""
	r = prep_request()
	response = r.get(su, timeout=90)
	soup = BeautifulSoup(response.content, 'xml')
	filer = soup.find('Filer')
	ein = filer.find('EIN').text
	org_name = filer.find('BusinessName').text.strip().title()
	year = soup.find('TaxYr').text.strip()
	org_id = f'{org_name}_{year}'
	org_id = org_id.replace(' ', '_').lower()
	org_id = re.sub('[^a-zA-Z0-9 \n\.]', '', org_id)
	voting_members = soup.find('VotingMembersGoverningBodyCnt').text.strip()
	employees = soup.find('TotalEmployeeCnt').text.strip()
	employees = str_to_int(employees, "number")
	total_revenue = soup.find('CYTotalRevenueAmt').text.strip()
	total_revenue = str_to_int(total_revenue, "number")
	salaries = soup.find('CYSalariesCompEmpBnftPaidAmt').text.strip()
	salaries = str_to_int(salaries, "number")
	total_expenses = soup.find('CYTotalExpensesAmt').text.strip()
	total_expenses = str_to_int(total_expenses, "number")
	rev_minus_exp = soup.find('CYRevenuesLessExpensesAmt').text.strip()
	rev_minus_exp = str_to_int(rev_minus_exp, "number")
	assets = soup.find('NetAssetsOrFundBalancesEOYAmt').text.strip()
	assets = str_to_int(assets, "number")
	print(f'Processing data from {org_name} for {year}\n')
	comp_total = 0
	comp_list = []
	for x in soup.find_all('Form990PartVIISectionAGrp'):
		tag_list = []
		#print("---")
		name = x.find('PersonNm').text.strip().title()
		job_title = x.find('TitleTxt').text.strip().title()
		comp = x.find('ReportableCompFromOrgAmt').text.strip()
		reportable_comp = x.find('ReportableCompFromRltdOrgAmt').text.strip()
		other_comp = x.find('OtherCompensationAmt').text.strip()
		comp = str_to_int(comp, "number")
		reportable_comp = str_to_int(reportable_comp, "number")
		other_comp = str_to_int(other_comp, "number")
		total_comp = comp + reportable_comp + other_comp
		comp_list.append(total_comp)
		for tag in x:
			tn = tag.name
			tt = tag.text.strip().title()
			#print(tt)
			if tn not in tag_list and tn != None:
				tag_list.append(tn)
		#print(tag_list)
		if "IndividualTrusteeOrDirectorInd" in tag_list:
			role = "Board Member"
		elif "InstitutionalTrusteeInd" in tag_list:
			role = "Board Member"
		else:
			role = "Employee"
		comp_total = comp_total + total_comp
		df_people.loc[df_people.shape[0]] = [org_id, org_name, year, name, role, job_title, comp, reportable_comp, other_comp, total_comp]
	comp_list.sort(reverse=True)
	high = comp_list[0]
	# get highest compensated employee 
	# TODO - add logic to address the possibility of two or more people being the highest earners
	df_highest = df_people[(df_people['total_comp'] == high) & (df_people['year'] == year) & (df_people['org_name'] == org_name)]
	highest_comp_name = df_highest['name'].iloc[0]
	highest_comp_title = df_highest['job_title'].iloc[0]
	highest_comp_amount = high
	df_orgs.loc[df_orgs.shape[0]] = [org_id, ein, org_name, year, voting_members, employees, total_revenue, salaries, total_expenses, rev_minus_exp, assets, highest_comp_name, highest_comp_title, highest_comp_amount]
	df_salary_calc = df_people[(df_people['total_comp'] > 0) & (df_people['year'] == year) & (df_people['org_name'] == org_name)]
	listed_salary = df_salary_calc.shape[0]
	total_listed_salary = df_salary_calc.loc[:, 'total_comp'].sum()
	comp_summary = ""
	comp_summary = f'<p><b>Total people with listed compensation</b>: {listed_salary}<br><b>Sum, compensation</b>: ${total_listed_salary:,}</p>'
	avg_salary_listed = round(total_listed_salary / listed_salary, 0)
	'''
	# calculate average salary for those not listed
	remaining_emp = employees - listed_salary
	if remaining_emp > 0:
		remaining_comp = salaries - total_listed_salary
		avg_salary_workforce = round(remaining_comp / remaining_emp, 2)
		work = f'<b>Average compensation of other employees (rough estimate)</b>: ${avg_salary_workforce:,}</p>'
	else:
		work = '</p>'
	'''
	
	percent_listed = round((listed_salary / employees) * 100, 3)
	percent_salary = round((total_listed_salary / salaries) * 100, 3)
	comp_summary = comp_summary + f'<p><b>Percent of people with listed salaries</b>: {percent_listed} %<br><b>Percent of all salaries they earn</b>: {percent_salary} %<br>' \
								f'<b>Average compensation of people listed on Form 990</b>: ${avg_salary_listed:,}<br></p>' \
								f'<p>Average salary/compensation estimates are very rough because, in some cases, the numbers include expenses for benefits, and these costs might not be readily visible in an employee\'s paycheck.</p>'

	## Generate summary
	intro = ""
	intro = f'<h2><a id="{org_id}">{org_name} - {year}</h2>\n<h3>1. Overview</h3>\n\n<ul>\n' \
		f'<li><b>Employees</b>: {employees}</li>\n<li><b>Total Revenue</b>: ${total_revenue:,}</li>\n<li><b>Salaries and Benefits</b>: ${salaries:,}</li>\n' \
		f'<li><b>Total Expenses</b>: ${total_expenses:,}</li>\n<li><b>Revenue minus expenses</b>: ${rev_minus_exp:,}</li>\n<li><b>Assets</b>: ${assets:,}</li>\n</ul>\n\n' \
		f'<h3>2. Highest paid employee</h3>\n<b>{highest_comp_name}</b>, {highest_comp_title}<br>Compensation: ${highest_comp_amount:,}\n\n'
	# Generate Board Report
	board = ""
	section = 3
	if show_board == "Yes":
		board = f"<h3>{section}. Board</h3>"
		section = section + 1
		df_board = df_people[(df_people['org_id'] == org_id) & (df_people['role'] == "Board Member")]
		df_board = df_board.sort_values(['name'], ascending = [True])
		for a, b in df_board.iterrows():
			b_name = b['name']
			b_job_title = b['job_title']
			b_comp = b['total_comp']
			board = board + f'<p><b>{b_name}</b>, {b_job_title}<br>Total compensation: ${b_comp:,}</p>'
		board = board + "<hr>"
	else:
		pass

	# Generate Staff Report
	# Generate Board Report
	staff = ""
	if show_staff == "Yes":
		staff = f"<h3>{section}. {org_name} Staff for {year}</h3>\n\n"
		section = section + 1
		df_staff = df_people[(df_people['org_id'] == org_id) & (df_people['role'] == "Employee")]
		df_staff = df_staff.sort_values(['name'], ascending = [True])
		for a, b in df_staff.iterrows():
			b_name = b['name']
			b_job_title = b['job_title']
			b_comp = b['total_comp']
			staff = staff + f'<p><b>{b_name}</b>, {b_job_title}<br>Total compensation: ${b_comp:,}<p>'
		staff = staff + "\n"
	else:
		pass

	sum_num = ""
	sum_num = f'<h3>{section}. Summary numbers</h3><p>The calculations included here are intended to surface other areas to research, or ' \
			f'places that need more examination. Something that looks off here should not be taken as a problem; these numbers ' \
			f'are intended to highlight places for additional review.<p>{comp_summary}'

	summary_text = intro + board + staff + sum_num
	df_report.loc[df_report.shape[0]] = [org_id, summary_text]


# sort dataframes; save to csv
df_people = df_people.sort_values(['org_name', 'year'], ascending = [True, False])
df_orgs = df_orgs.sort_values(['org_name', 'year'], ascending = [True, False])
df_people.to_csv('people.csv', encoding='utf-8', index=False)
df_orgs.to_csv('orgs.csv', encoding='utf-8', index=False)

# organize and output summary
doc_intro = '<h2>Summary of Form 990s</h2>\n\nFor more information and full reports, see ProPublica\'s <a href="https://projects.propublica.org/nonprofits/" title="ProPublica NonProfit Explorer">ProPublica Database of Form 990s</a>\n<ul>'
doc_body = ""
for x, y in df_orgs.iterrows():
	organization = y['org_name']
	organization_id = y['org_id']
	year = y['year']
	doc_intro = doc_intro + f'<li><a href="#{organization_id}" title="Jump to details for {organization} in {year}">{organization} - {year}</a></li>'
	df_body = df_report[df_report['org_id'] == organization_id]
	doc_body = doc_body + df_body['summary_text'].iloc[0] + "\n<hr>\n"

doc_intro = doc_intro + "</ul>"

full_doc = doc_intro + doc_body

write_file(html_filename, full_doc)

# open in web browser
webbrowser.open(html_filename)

