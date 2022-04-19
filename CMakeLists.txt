cmake_minimum_required(VERSION 3.12)

project(ShapeSimplification VERSION 0.1
        DESCRIPTION "SnapPea"
        LANGUAGES CXX)

set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native")
set(CMAKE_CXX_STANDARD 17)


include_directories(kernel/addl_code kernel/headers kernel/real_type)

set(C_FILES
	kernel/kernel_code
	kernel/addl_code
	kernel/addl_code/isomorphism_signature.c
)

# main
add_executable(SnapPyMieux
			   ${C_FILES}
			   main.cpp
)

